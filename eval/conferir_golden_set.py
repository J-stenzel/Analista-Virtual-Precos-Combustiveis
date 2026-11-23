"""
Confere o golden set (eval/golden_set.csv) contra o banco.

Rodar a partir da raiz do projeto, com o venv ativo:
    python eval/conferir_golden_set.py            # resumo
    python eval/conferir_golden_set.py --detalhe  # mostra o resultado de cada SQL

O que é conferido:
  1. Estrutura: colunas do enunciado, 20 perguntas, ids únicos, distribuição 7 fáceis / 7 médias / 4 difíceis / 2 armadilhas.
  2. Armadilhas NÃO têm SQL (o certo é pedir esclarecimento ou recusar).
  3. Todo sql_referencia é somente leitura (começa com SELECT/WITH, sem INSERT/UPDATE/DELETE/DROP/ALTER)
     e não usa a data do relógio (R01: nada de CURRENT_DATE / now() / today()).
  4. Todo sql_referencia roda no banco e devolve pelo menos 1 linha.
  5. Nenhuma pergunta do golden set aparece no semantic_layer.yaml (senão o agente "cola" a resposta da prova).

Este script é a base do eval/run_eval.py (Etapa 4). Sai com código 1 se algo falhar.
"""
import collections
import csv
import re
import sys
from pathlib import Path

import duckdb

sys.stdout.reconfigure(encoding="utf-8")   # acentos no terminal do Windows

RAIZ = Path(__file__).resolve().parents[1]
CSV_PATH = RAIZ / "eval" / "golden_set.csv"
DB_PATH = RAIZ / "data" / "processed" / "combustiveis.duckdb"
YAML_PATH = RAIZ / "src" / "semantic_layer.yaml"
DETALHE = "--detalhe" in sys.argv

falhas = []


def checa(descricao, ok, detalhe=""):
    print(f"  {'OK  ' if ok else 'FALHA'} {descricao} {detalhe}")
    if not ok:
        falhas.append(descricao)


# utf-8-sig: o arquivo tem BOM para o Excel abrir os acentos corretamente
with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
    leitor = csv.DictReader(f)
    colunas = leitor.fieldnames
    perguntas = list(leitor)

# ---------------------------------------------------------------------------
print("\n1. Estrutura")
for col in ["pergunta", "sql_referencia", "resposta_esperada", "nivel"]:   # colunas exigidas pelo enunciado
    checa(f"coluna '{col}' existe", col in colunas)
checa("20 perguntas", len(perguntas) == 20, f"({len(perguntas)})")
ids = [p["id"] for p in perguntas]
checa("ids únicos", len(ids) == len(set(ids)))
contagem = collections.Counter(p["nivel"] for p in perguntas)
esperado = {"facil": 7, "medio": 7, "dificil": 4, "armadilha": 2}
checa("distribuição 7/7/4/2", dict(contagem) == esperado, str(dict(contagem)))
checa("toda pergunta tem resposta esperada", all(p["resposta_esperada"].strip() for p in perguntas))

# ---------------------------------------------------------------------------
print("\n2. Armadilhas sem SQL")
for p in perguntas:
    if p["nivel"] == "armadilha":
        checa(f"#{p['id']} sem SQL", not p["sql_referencia"].strip())

# ---------------------------------------------------------------------------
print("\n3 e 4. SQL de referência: somente leitura, sem relógio, roda no banco")
PROIBIDOS = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|COPY)\b", re.I)
RELOGIO = re.compile(r"\b(CURRENT_DATE|CURRENT_TIMESTAMP|NOW\(|TODAY\()", re.I)
con = duckdb.connect(str(DB_PATH), read_only=True)   # somente leitura, como os agentes
for p in perguntas:
    sql = p["sql_referencia"].strip()
    if p["nivel"] == "armadilha":
        continue
    sem_comentarios = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    ok_leitura = sem_comentarios.strip().upper().startswith(("SELECT", "WITH")) and not PROIBIDOS.search(sem_comentarios)
    ok_relogio = not RELOGIO.search(sem_comentarios)
    try:
        df = con.execute(sql).df()
        ok_roda, info = len(df) > 0, f"({len(df)} linhas)"
    except Exception as erro:          # noqa: BLE001 — registrar qualquer erro de SQL
        df, ok_roda, info = None, False, f"ERRO: {erro}"
    checa(f"#{p['id']:>2} [{p['nivel']}]", ok_leitura and ok_relogio and ok_roda,
          info + ("" if ok_leitura else " NÃO É SOMENTE LEITURA") + ("" if ok_relogio else " USA O RELÓGIO (R01)"))
    # Critério de correção: toda coluna-chave precisa existir no resultado da referência
    chaves = [c.strip() for c in p.get("colunas_chave", "").split(",") if c.strip()]
    if df is not None:
        faltando = [c for c in chaves if c not in df.columns]
        checa(f"#{p['id']:>2} colunas_chave definidas e existentes", bool(chaves) and not faltando,
              f"{chaves}" + (f" FALTANDO: {faltando}" if faltando else ""))
    if DETALHE and df is not None:
        print("     ", p["pergunta"])
        print(df.head(12).to_string(index=False).replace("\n", "\n      "))
con.close()

# ---------------------------------------------------------------------------
print("\n5. Perguntas do golden set fora do semantic_layer.yaml")
texto_yaml = YAML_PATH.read_text(encoding="utf-8").lower()
vazadas = [p["id"] for p in perguntas if p["pergunta"].lower().rstrip("?") in texto_yaml]
checa("nenhuma pergunta copiada no YAML", not vazadas, f"(vazadas: {vazadas})" if vazadas else "")

print("\n" + ("GOLDEN SET OK ✅" if not falhas else f"{len(falhas)} FALHA(S) ❌: {falhas}"))
sys.exit(1 if falhas else 0)
