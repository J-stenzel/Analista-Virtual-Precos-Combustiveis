"""
Geocodifica os postos (endereço -> latitude/longitude) com a Google Geocoding API. Complemento 5.13 (postos próximos).

Uso (na raiz do projeto, com o venv ativo):
    python src/geocodificar_postos.py --uf SP              # postos de SP com coleta na janela recente
    python src/geocodificar_postos.py --uf SP --simular    # só mostra quantos seriam consultados (sem gastar)

Saída: data/processed/postos_geo.csv (1 linha por posto; FORA do GitHub). Depois rode `python src/load_data.py`
para levar as coordenadas à dim_posto (colunas latitude, longitude, precisao_geo, geocodificado_em).

Cuidados:
  - Chave em GOOGLE_MAPS_API_KEY no .env (nunca no código). A chave nunca é impressa.
  - CACHE: posto já geocodificado não é consultado de novo (retoma de onde parou; não paga duas vezes).
  - TETO: --max (padrão 2.500) consultas por execução, abaixo da cota grátis do Google (10 mil/mês).
  - Termos do Google: coordenadas podem ser guardadas por até 30 dias -> a coluna geocodificado_em diz quando
    apagar ou refazer (decisão do aluno: ele fará a exclusão).
  - Validação: se o ponto cair FORA do município do posto, tenta de novo só pelo CEP; se ainda falhar, marca
    NAO_ENCONTRADO (o posto fica sem coordenada e não entra nas buscas por distância).
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import duckdb
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]
load_dotenv(RAIZ / ".env")
DB = RAIZ / "data" / "processed" / "combustiveis.duckdb"
SAIDA = RAIZ / "data" / "processed" / "postos_geo.csv"
URL = "https://maps.googleapis.com/maps/api/geocode/json"
COLUNAS = ["cnpj", "latitude", "longitude", "precisao_geo", "tipo_busca", "endereco_google", "status",
           "geocodificado_em"]
PAUSA_S = 0.1          # ~10 consultas/s (o Google aceita bem mais; não há pressa)


def sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn").upper()


def postos_a_geocodificar(uf: str) -> list[dict]:
    """Postos da UF com coleta na janela recente (últimos 3 meses até o último mês da base, R06)."""
    con = duckdb.connect(str(DB), read_only=True)
    linhas = con.execute("""
        WITH janela AS (SELECT strftime(MAX(data) - INTERVAL 2 MONTH, '%Y-%m') AS inicio FROM fato_precos)
        SELECT DISTINCT p.cnpj, p.endereco, p.numero, p.bairro, p.cep, l.municipio, l.uf
        FROM fato_precos f
        JOIN dim_posto p USING (cnpj)
        JOIN dim_local l USING (id_local)
        JOIN dim_tempo t USING (data)
        WHERE l.uf = ? AND t.ano_mes >= (SELECT inicio FROM janela)
        ORDER BY p.cnpj
    """, [uf]).fetchall()
    con.close()
    vistos, postos = set(), []
    for cnpj, endereco, numero, bairro, cep, municipio, uf_ in linhas:
        if cnpj not in vistos:            # posto que mudou de município: fica o 1º (raro)
            vistos.add(cnpj)
            postos.append({"cnpj": cnpj, "endereco": endereco, "numero": numero, "bairro": bairro, "cep": cep,
                           "municipio": municipio, "uf": uf_})
    return postos


def ja_feitos() -> set[str]:
    if not SAIDA.exists():
        return set()
    with open(SAIDA, encoding="utf-8", newline="") as f:
        return {linha["cnpj"] for linha in csv.DictReader(f)}


def consultar(endereco: str, chave: str, tentativas: int = 3) -> dict:
    """Uma consulta à API. Falha de REDE (conexão caiu, timeout) -> tenta de novo com espera crescente (2 s, 4 s).
    Correção de 24/11: a 1ª carga parou no posto 512 com 'conexão cancelada pelo host remoto' (WinError 10054)."""
    parametros = {"address": endereco, "region": "br", "components": "country:BR", "key": chave}
    for tentativa in range(1, tentativas + 1):
        try:
            with urllib.request.urlopen(URL + "?" + urllib.parse.urlencode(parametros), timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as erro:
            if tentativa == tentativas:
                # mensagem sem a URL (que contém a chave)
                raise SystemExit(f"⛔ Falha de rede {tentativas}x seguidas ({type(erro).__name__}) — parado; "
                                 "o que já foi feito está salvo. Rode de novo para continuar.") from None
            time.sleep(2 * tentativa)


def no_municipio_certo(resultado: dict, posto: dict) -> bool:
    """O ponto devolvido está no município e na UF do posto? (evita rua homônima em outra cidade)"""
    nomes = {sem_acento(c["long_name"]) for c in resultado.get("address_components", [])}
    curtos = {c["short_name"].upper() for c in resultado.get("address_components", [])}
    return sem_acento(posto["municipio"]) in nomes and posto["uf"] in curtos


def montar_endereco(posto: dict) -> str:
    numero = (posto["numero"] or "").replace(".", "").strip()          # "1.431" -> "1431"
    if not re.search(r"\d", numero):                                      # "S/N", "SN", vazio
        numero = ""
    partes = [posto["endereco"], numero, posto["bairro"], f"{posto['municipio']} - {posto['uf']}", posto["cep"]]
    return ", ".join(p for p in partes if p) + ", Brasil"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Geocodifica postos com a Google Geocoding API")
    parser.add_argument("--uf", required=True, help="sigla da UF (ex.: SP)")
    parser.add_argument("--max", type=int, default=2500, help="teto de consultas nesta execução")
    parser.add_argument("--simular", action="store_true", help="só conta, não consulta a API")
    args = parser.parse_args()

    postos = postos_a_geocodificar(args.uf.upper())
    feitos = ja_feitos()
    pendentes = [p for p in postos if p["cnpj"] not in feitos]
    print(f"{args.uf.upper()}: {len(postos)} postos na janela recente; {len(feitos)} já no cache; "
          f"{len(pendentes)} a consultar (até ~{2 * len(pendentes)} consultas no pior caso; teto {args.max})")
    if args.simular or not pendentes:
        return
    chave = os.getenv("GOOGLE_MAPS_API_KEY")
    if not chave:
        sys.exit("GOOGLE_MAPS_API_KEY não encontrada no .env")

    novo = not SAIDA.exists()
    consultas, contagem = 0, {}
    hoje = datetime.date.today().isoformat()
    with open(SAIDA, "a", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS)
        if novo:
            escritor.writeheader()
        for i, posto in enumerate(pendentes, start=1):
            linha = {"cnpj": posto["cnpj"], "geocodificado_em": hoje, "status": "NAO_ENCONTRADO"}
            # 1ª tentativa: endereço completo; 2ª: só CEP + município (se a 1ª caiu fora do município)
            for tipo, texto in [("endereco", montar_endereco(posto)),
                                ("cep", f"{posto['cep']}, {posto['municipio']} - {posto['uf']}, Brasil")]:
                if consultas >= args.max:
                    print(f"⛔ Teto de {args.max} consultas atingido — rode de novo depois (o cache continua daqui).")
                    return
                if tipo == "cep" and not posto["cep"]:
                    break
                resposta = consultar(texto, chave)
                consultas += 1
                time.sleep(PAUSA_S)
                status = resposta.get("status")
                if status in ("OVER_QUERY_LIMIT", "OVER_DAILY_LIMIT", "REQUEST_DENIED", "INVALID_REQUEST"):
                    sys.exit(f"⛔ Google recusou ({status}): {resposta.get('error_message', '')[:200]} — parado; "
                             "o que já foi feito está salvo.")
                if status == "OK" and no_municipio_certo(resposta["results"][0], posto):
                    r = resposta["results"][0]
                    linha.update({"latitude": r["geometry"]["location"]["lat"],
                                  "longitude": r["geometry"]["location"]["lng"],
                                  "precisao_geo": r["geometry"]["location_type"], "tipo_busca": tipo,
                                  "endereco_google": r["formatted_address"], "status": "OK"})
                    break
            escritor.writerow(linha)
            f.flush()                                    # grava já: se cair, nada se perde
            chave_contagem = f"{linha['status']} / {linha.get('tipo_busca', '-')} / {linha.get('precisao_geo', '-')}"
            contagem[chave_contagem] = contagem.get(chave_contagem, 0) + 1
            if i % 100 == 0:
                print(f"  {i}/{len(pendentes)} postos · {consultas} consultas")

    print(f"\nConcluído: {len(pendentes)} postos, {consultas} consultas à API ({consultas / 100:.1f}% da cota grátis mensal)")
    for k, v in sorted(contagem.items(), key=lambda x: -x[1]):
        print(f"  {v:5d}  {k}")
    print(f"Resultado em {SAIDA.relative_to(RAIZ)}. Próximo passo: python src/load_data.py")


if __name__ == "__main__":
    main()
