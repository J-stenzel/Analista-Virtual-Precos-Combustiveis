"""
Compara o resultado obtido pelo agente com o resultado do SQL de referência.

Critério (o mesmo vale para as perguntas de desenvolvimento e, na Etapa 4, para o golden set):
  - Compara VALORES, não o texto do SQL: um SQL diferente que chega aos mesmos números está certo.
  - Ignora nomes e ordem das colunas e a ordem das linhas.
  - Ignora colunas de data (período da amostra): elas aparecem no texto da resposta (R09), não no "número".
  - Números batem com tolerância (arredondamentos diferentes: 7,461 x 7,46).
  - Cada linha da referência precisa encontrar uma linha do agente que contenha TODOS os seus valores.
    O agente pode trazer colunas a mais (não penaliza).
  - colunas_chave (opcional, definido por pergunta no CSV): só os valores dessas colunas da referência
    precisam bater. Ex.: no "menor preço", a chave é o preço; colunas de contexto (nº de postos) não contam.
"""
import math
import re

DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _normalizar(valor):
    """Número -> float; texto -> MAIÚSCULO sem espaços nas pontas; data/booleano/nulo -> None (ignorado)."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return None if (isinstance(valor, float) and math.isnan(valor)) else float(valor)
    texto = str(valor).strip()
    if DATA_ISO.match(texto):
        return None
    try:
        return float(texto.replace(",", "."))
    except ValueError:
        return texto.upper()


def _casas_decimais(valor) -> int:
    """Quantas casas decimais o valor da REFERÊNCIA tem (5.3 -> 1; 7.461 -> 3; inteiros -> 0)."""
    if isinstance(valor, bool) or not isinstance(valor, (float, str)):
        return 0
    texto = repr(valor) if isinstance(valor, float) else valor.strip()
    if "e" in texto.lower() or "." not in texto:
        return 0
    return len(texto.split(".")[1].rstrip("0"))


def _bate(ref, obtido, casas: int = 0) -> bool:
    if isinstance(ref, float) and isinstance(obtido, float):
        tolerancia = max(0.01, abs(ref) * 0.001)
        if casas > 0:
            # Correção de 23/11: a referência pode estar ARREDONDADA (5,3); um valor do agente que arredonda para
            # ela (5,33) é o mesmo número. Só vale para valores com casas decimais (contagens continuam exatas).
            tolerancia = max(tolerancia, 0.5 * 10 ** -casas + 1e-9)
        return abs(ref - obtido) <= tolerancia
    return ref == obtido


def _linha_contem(linha_ref: list, linha_obtida: list) -> bool:
    """Todos os valores (não ignorados) da linha de referência aparecem na linha obtida?"""
    disponiveis = [_normalizar(v) for v in linha_obtida]
    for original in linha_ref:
        valor, casas = _normalizar(original), _casas_decimais(original)
        if valor is None:
            continue
        indice = next((i for i, d in enumerate(disponiveis) if d is not None and _bate(valor, d, casas)), None)
        if indice is None:
            return False
        disponiveis[indice] = None          # cada valor obtido só pode ser usado uma vez
    return True


def comparar(linhas_ref: list, linhas_obtidas: list | None,
             colunas_ref: list | None = None, colunas_chave: list | None = None) -> dict:
    """Devolve {"acerto": bool, "linhas_ref", "linhas_encontradas", "detalhe"}."""
    if colunas_chave:
        faltando = [c for c in colunas_chave if c not in (colunas_ref or [])]
        if faltando:
            raise ValueError(f"colunas_chave {faltando} não existem no resultado da referência {colunas_ref}")
        indices = [colunas_ref.index(c) for c in colunas_chave]
        linhas_ref = [[linha[i] for i in indices] for linha in linhas_ref]
    if not linhas_obtidas:
        return {"acerto": False, "linhas_ref": len(linhas_ref), "linhas_encontradas": 0,
                "detalhe": "o agente não executou nenhuma consulta com resultado"}
    livres = list(range(len(linhas_obtidas)))
    encontradas = 0
    for linha_ref in linhas_ref:
        achou = next((i for i in livres if _linha_contem(linha_ref, linhas_obtidas[i])), None)
        if achou is not None:
            livres.remove(achou)
            encontradas += 1
    acerto = encontradas == len(linhas_ref)
    detalhe = "" if acerto else f"{len(linhas_ref) - encontradas} de {len(linhas_ref)} linhas da referência sem correspondência"
    return {"acerto": acerto, "linhas_ref": len(linhas_ref), "linhas_encontradas": encontradas, "detalhe": detalhe}


# ---------------------------------------------------------------------------
# Apresentação da resposta (texto + tabela + SQL usado) — igual para todos os agentes
# ---------------------------------------------------------------------------
def formatar_resposta(res: dict, max_linhas: int = 20) -> str:
    partes = [f"[{res['classe']}] {res['resposta']}"]
    if res.get("linhas"):
        partes.append("\nTabela:")
        partes.append("  " + " | ".join(res["colunas"]))
        for linha in res["linhas"][:max_linhas]:
            partes.append("  " + " | ".join("" if v is None else str(v) for v in linha))
        if len(res["linhas"]) > max_linhas:
            partes.append(f"  ... ({len(res['linhas'])} linhas no total)")
        partes.append("\nSQL usado:\n" + res["sql"])
    u = res["uso"]
    partes.append(f"\n[{res['tempo_s']} s · {u['chamadas_llm']} chamadas à LLM · {res['tentativas_run_sql']} execução(ões) "
                  f"de SQL · tokens {u['tokens_entrada']} entrada ({u['tokens_cache']} em cache) / {u['tokens_saida']} saída "
                  f"· US$ {u['custo_usd']:.4f}]")
    for agente, ua in (res.get("uso_por_agente") or {}).items():
        partes.append(f"   - {agente:12} {ua['tempo_s']:>5} s · {ua['chamadas_llm']} chamada(s) · US$ {ua['custo_usd']:.4f}")
    return "\n".join(partes)


# ---------------------------------------------------------------------------
# Corrigir UMA resposta contra a pergunta do CSV (mesma régua para dev, golden "antes" e "depois")
# ---------------------------------------------------------------------------
def avaliar_resposta(p: dict, res: dict) -> tuple:
    """Devolve (acerto, classe_esperada, detalhe). p = linha do CSV; res = saída do responder()."""
    import tools
    if p["sql_referencia"].strip():
        referencia = tools.run_sql(p["sql_referencia"], limite=tools.LIMITE_MAXIMO)
        chave = [c.strip() for c in p.get("colunas_chave", "").split(",") if c.strip()] or None
        comp = comparar(referencia["linhas"], res["linhas"], referencia["colunas"], chave)
        acerto = res["classe"] == "DADOS" and comp["acerto"]
        detalhe = comp["detalhe"] if res["classe"] == "DADOS" else f"classe {res['classe']} (esperado DADOS)"
        return acerto, "DADOS", detalhe
    esperado = "ESCLARECIMENTO" if p["resposta_esperada"].startswith("PEDIR") else "FORA_DE_ESCOPO"
    acerto = res["classe"] == esperado and res["tentativas_run_sql"] == 0
    detalhe = "" if acerto else f"classe {res['classe']} (esperado {esperado}), {res['tentativas_run_sql']} SQL executado(s)"
    return acerto, esperado, detalhe


# ---------------------------------------------------------------------------
# Rodar um conjunto de perguntas (dev agora; golden set na Etapa 4) e medir
# ---------------------------------------------------------------------------
def rodar_perguntas(responder, arquivo: str = "perguntas_dev.csv", ids: set | None = None,
                    rotulo: str = "dev") -> list:
    """Roda `responder(pergunta)` em cada pergunta do CSV, compara com a referência e imprime o placar."""
    import csv
    import datetime
    import json
    from pathlib import Path

    import llm
    import tools

    raiz = Path(__file__).resolve().parents[1]
    with open(raiz / "eval" / arquivo, encoding="utf-8-sig", newline="") as f:
        perguntas = [p for p in csv.DictReader(f) if not ids or p["id"] in ids]
    registros = []
    for p in perguntas:
        print(f"\n=== {p['id']} [{p['nivel']}] {p['pergunta']}")
        try:
            res = responder(p["pergunta"])
        except llm.ErroLLM as erro:
            print("   ERRO DA LLM:", erro)
            break
        acerto, esperado, detalhe = avaliar_resposta(p, res)
        print(formatar_resposta(res, max_linhas=8))
        print(f"   >>> {'✅ ACERTO' if acerto else '❌ ERRO'} {detalhe}")
        registros.append({"id": p["id"], "nivel": p["nivel"], "acerto": acerto, "esperado": esperado,
                          "detalhe": detalhe, **res})

    if not registros:
        return registros
    n = len(registros)
    acertos = sum(r["acerto"] for r in registros)
    com_sql = [r for r in registros if r["sql_ok_1a_tentativa"] is not None]
    print(f"\n================ RESUMO ({rotulo}) ================")
    print(f"Acurácia: {acertos}/{n} ({100 * acertos / n:.0f}%)")
    if com_sql:
        print(f"SQL válido na 1ª tentativa: {sum(r['sql_ok_1a_tentativa'] for r in com_sql)}/{len(com_sql)}")
        print(f"Média de execuções de SQL: {sum(r['tentativas_run_sql'] for r in com_sql) / len(com_sql):.2f}")
    print(f"Tempo médio: {sum(r['tempo_s'] for r in registros) / n:.1f} s")
    custo = sum(r["uso"]["custo_usd"] for r in registros)
    print(f"Custo total: US$ {custo:.4f} (média US$ {custo / n:.4f} por pergunta)")
    agentes = {a for r in registros for a in (r.get("uso_por_agente") or {})}
    for a in sorted(agentes):
        usos = [r["uso_por_agente"][a] for r in registros if a in (r.get("uso_por_agente") or {})]
        print(f"   - {a:12} custo US$ {sum(u['custo_usd'] for u in usos):.4f} · tempo médio "
              f"{sum(u['tempo_s'] for u in usos) / len(usos):.1f} s ({len(usos)} perguntas)")
    destino = raiz / "logs" / f"{rotulo}_{datetime.datetime.now():%Y%m%d_%H%M%S}.jsonl"
    destino.parent.mkdir(exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        for r in registros:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    print(f"Detalhes salvos em {destino.relative_to(raiz)}")
    return registros
