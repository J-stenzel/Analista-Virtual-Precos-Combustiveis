"""
Avaliação oficial com o GOLDEN SET (Etapa 4).

Uso (na raiz do projeto, com o venv ativo):
    python eval/run_eval.py --rodada antes          # roda as 20 perguntas pelos 3 agentes e grava os resultados
    python eval/run_eval.py --rodada depois
    python eval/run_eval.py --resumo                # só mostra as métricas de todas as rodadas já gravadas
    python eval/run_eval.py --recomparar antes      # recalcula os acertos de uma rodada com o comparador atual (sem LLM)

Saídas:
    eval/resultados.csv            uma linha por pergunta e rodada (exigido pelo enunciado)
    eval/detalhes/<rodada>.jsonl   resposta, tabela e SQL de cada pergunta (base do analise_erros.md)

Regras desta avaliação:
  - Cache da LLM SEMPRE desligado (tempo e custo precisam ser reais).
  - O critério de acerto é o do golden set (colunas_chave), definido ANTES da 1ª rodada.
  - acerto_automatico = comparador; acerto_final começa igual. Se a revisão manual mudar algum resultado,
    a mudança vai em acerto_final COM justificativa na coluna "revisao" (vale igual para todas as rodadas).
  - Uma rodada já gravada não é sobrescrita sem --substituir (protege a medição "antes").
"""
import csv
import datetime
import json
import os
import sys
from pathlib import Path

os.environ["LLM_CACHE"] = "0"          # antes de importar o llm: o .env não consegue religar o cache

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
import avaliacao      # noqa: E402
import llm            # noqa: E402
import orchestrator   # noqa: E402

RESULTADOS = RAIZ / "eval" / "resultados.csv"
DETALHES = RAIZ / "eval" / "detalhes"
COLUNAS = ["rodada", "data_hora", "id", "nivel", "esperado", "classe", "acerto_automatico", "acerto_final", "revisao",
           "sql_valido_1a", "tentativas_run_sql", "tentativas_correcao", "tempo_s", "tokens_entrada", "tokens_cache",
           "tokens_saida", "custo_usd", "modelo_orquestrador", "modelo_sql", "modelo_analista", "detalhe"]


def _ler_resultados() -> list:
    if not RESULTADOS.exists():
        return []
    with open(RESULTADOS, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _gravar_resultados(linhas: list) -> None:
    with open(RESULTADOS, "w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS)
        escritor.writeheader()
        escritor.writerows(linhas)


def metricas(linhas: list) -> dict:
    """As métricas pedidas pelo enunciado, calculadas a partir das linhas de UMA rodada."""
    n = len(linhas)
    verdadeiro = lambda v: str(v) == "True"
    com_sql = [l for l in linhas if l["sql_valido_1a"] in ("True", "False")]
    por_nivel = {}
    for l in linhas:
        a, t = por_nivel.get(l["nivel"], (0, 0))
        por_nivel[l["nivel"]] = (a + verdadeiro(l["acerto_final"]), t + 1)
    return {
        "perguntas": n,
        "acuracia": sum(verdadeiro(l["acerto_final"]) for l in linhas) / n if n else 0,
        "por_nivel": por_nivel,
        "sql_valido_1a": (sum(verdadeiro(l["sql_valido_1a"]) for l in com_sql) / len(com_sql)) if com_sql else 0,
        "perguntas_com_sql": len(com_sql),
        "media_tentativas_correcao": (sum(int(l["tentativas_correcao"]) for l in com_sql) / len(com_sql)) if com_sql else 0,
        "tempo_medio_s": sum(float(l["tempo_s"]) for l in linhas) / n if n else 0,
        "custo_total_usd": sum(float(l["custo_usd"]) for l in linhas),
        "tokens_total": sum(int(l["tokens_entrada"]) + int(l["tokens_saida"]) for l in linhas),
    }


def imprimir_resumo() -> None:
    linhas = _ler_resultados()
    rodadas = list(dict.fromkeys(l["rodada"] for l in linhas))
    if not rodadas:
        print("Nenhuma rodada gravada ainda.")
        return
    print(f"\n{'métrica':34}" + "".join(f"{r:>16}" for r in rodadas))
    ms = {r: metricas([l for l in linhas if l["rodada"] == r]) for r in rodadas}
    def linha(nome, f):
        print(f"{nome:34}" + "".join(f"{f(ms[r]):>16}" for r in rodadas))
    linha("Acurácia", lambda m: f"{m['acuracia']:.0%} ({round(m['acuracia'] * m['perguntas'])}/{m['perguntas']})")
    for nivel in ("facil", "medio", "dificil", "armadilha"):
        linha(f"  {nivel}", lambda m, n=nivel: "{}/{}".format(*m["por_nivel"].get(n, (0, 0))))
    linha("SQL válido na 1ª tentativa", lambda m: f"{m['sql_valido_1a']:.0%}")
    linha("Média de tentativas de correção", lambda m: f"{m['media_tentativas_correcao']:.2f}")
    linha("Tempo médio de resposta", lambda m: f"{m['tempo_medio_s']:.1f} s")
    linha("Custo total (opcional)", lambda m: f"US$ {m['custo_total_usd']:.4f}")
    linha("Tokens totais (opcional)", lambda m: f"{m['tokens_total']:,}".replace(",", "."))


def rodar(rodada: str, substituir: bool) -> None:
    existentes = _ler_resultados()
    if any(l["rodada"] == rodada for l in existentes) and not substituir:
        sys.exit(f"A rodada '{rodada}' já está gravada em eval/resultados.csv. Use outro nome ou --substituir.")

    registros = avaliacao.rodar_perguntas(orchestrator.responder, arquivo="golden_set.csv", rotulo=f"golden_{rodada}")
    if len(registros) < 20:
        print(f"\n⚠️ Só {len(registros)} de 20 perguntas foram respondidas (erro da LLM?). Nada foi gravado.")
        return

    agora = datetime.datetime.now().isoformat(timespec="seconds")
    novas = []
    for r in registros:
        tentativas = r["tentativas_run_sql"]
        novas.append({
            "rodada": rodada, "data_hora": agora, "id": r["id"], "nivel": r["nivel"], "esperado": r["esperado"],
            "classe": r["classe"], "acerto_automatico": r["acerto"], "acerto_final": r["acerto"], "revisao": "",
            "sql_valido_1a": r["sql_ok_1a_tentativa"] if r["sql_ok_1a_tentativa"] is not None else "",
            "tentativas_run_sql": tentativas, "tentativas_correcao": max(tentativas - 1, 0) if tentativas else 0,
            "tempo_s": r["tempo_s"], "tokens_entrada": r["uso"]["tokens_entrada"], "tokens_cache": r["uso"]["tokens_cache"],
            "tokens_saida": r["uso"]["tokens_saida"], "custo_usd": r["uso"]["custo_usd"],
            "modelo_orquestrador": llm.MODELOS["orquestrador"], "modelo_sql": llm.MODELOS["sql"],
            "modelo_analista": llm.MODELOS["analista"], "detalhe": r["detalhe"],
        })
    _gravar_resultados([l for l in existentes if l["rodada"] != rodada] + novas)

    DETALHES.mkdir(exist_ok=True)
    with open(DETALHES / f"{rodada}.jsonl", "w", encoding="utf-8") as f:
        for r in registros:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    print(f"\nGravado: eval/resultados.csv (rodada '{rodada}') e eval/detalhes/{rodada}.jsonl")
    imprimir_resumo()


def recomparar(rodada: str) -> None:
    """Recalcula acerto_automatico de uma rodada com o comparador ATUAL, a partir das respostas gravadas
    (eval/detalhes/<rodada>.jsonl) — SEM chamar a LLM. Garante a mesma régua para "antes" e "depois".
    Se a pergunta já tinha revisão manual, acerto_final é mantido e a revisão ganha uma nota."""
    with open(RAIZ / "eval" / "golden_set.csv", encoding="utf-8-sig", newline="") as f:
        perguntas = {p["id"]: p for p in csv.DictReader(f)}
    with open(DETALHES / f"{rodada}.jsonl", encoding="utf-8") as f:
        respostas = {r["id"]: r for r in map(json.loads, f)}
    linhas = _ler_resultados()
    for l in linhas:
        if l["rodada"] != rodada or l["id"] not in respostas:
            continue
        acerto, _, detalhe = avaliacao.avaliar_resposta(perguntas[l["id"]], respostas[l["id"]])
        if str(acerto) != l["acerto_automatico"]:
            print(f"  #{l['id']}: acerto_automatico {l['acerto_automatico']} -> {acerto}")
        l["acerto_automatico"], l["detalhe"] = acerto, detalhe
        if l["revisao"]:
            if str(acerto) == l["acerto_final"] and "comparador atualizado" not in l["revisao"]:
                l["revisao"] += " | Comparador atualizado (23/11): o automático agora concorda com a revisão."
        else:
            l["acerto_final"] = acerto
    _gravar_resultados(linhas)
    print(f"Rodada '{rodada}' recomparada com o comparador atual.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--resumo" in sys.argv:
        imprimir_resumo()
    elif "--recomparar" in sys.argv and sys.argv.index("--recomparar") + 1 < len(sys.argv):
        recomparar(sys.argv[sys.argv.index("--recomparar") + 1])
        imprimir_resumo()
    elif "--rodada" in sys.argv and sys.argv.index("--rodada") + 1 < len(sys.argv):
        rodar(sys.argv[sys.argv.index("--rodada") + 1], "--substituir" in sys.argv)
    else:
        print(__doc__)
