"""
Fluxo entre os 3 agentes (Etapa 3.3).

    Pergunta -> ORQUESTRADOR -> (ESCLARECIMENTO / FORA_DE_ESCOPO: responde direto, sem SQL)
                             -> DADOS: AGENTE SQL -> AGENTE ANALISTA -> texto + tabela + SQL usado

Uso (na raiz do projeto, com o venv ativo):
    python src/orchestrator.py "qual o preço médio do etanol em Goiânia?"
    python src/orchestrator.py --chat            # conversa (permite responder a um pedido de esclarecimento)
    python src/orchestrator.py --dev             # perguntas de desenvolvimento + comparação com a referência
    python src/orchestrator.py --dev D1,D10
NUNCA rode com o golden set aqui: ele é só para as medições oficiais da Etapa 4.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agents      # noqa: E402
import avaliacao   # noqa: E402
import llm         # noqa: E402


def _somar(*usos: dict) -> dict:
    total = {"chamadas_llm": 0, "tokens_entrada": 0, "tokens_cache": 0, "tokens_saida": 0, "custo_usd": 0.0}
    for u in usos:
        for chave in total:
            total[chave] += u[chave]
    total["custo_usd"] = round(total["custo_usd"], 5)
    return total


def responder(pergunta: str, historico: list | None = None, ao_etapa=None) -> dict:
    """Responde UMA pergunta passando pelos 3 agentes. Mesmo formato de saída do agente único.
    ao_etapa (opcional): função chamada com "orquestrador", "sql" ou "analista" quando cada agente começa
    (a interface usa para mostrar o progresso; não muda a lógica)."""
    avisar = ao_etapa or (lambda etapa: None)
    inicio = time.perf_counter()
    avisar("orquestrador")
    orq = agents.orquestrador(pergunta, historico)
    usos = {"orquestrador": orq["uso"]}
    base = {"pergunta": pergunta, "classe": orq["classe"], "colunas": None, "linhas": None, "sql": None,
            "tentativas_run_sql": 0, "sql_ok_1a_tentativa": None, "erros_sql": [], "motivo_parada": "resposta",
            "pergunta_completa": orq["pergunta_completa"], "ressalvas": []}

    if orq["classe"] != "DADOS":                       # esclarecimento ou recusa: nenhum SQL é gerado
        resposta = orq["mensagem_usuario"] or "Não consegui interpretar a pergunta."
    else:
        avisar("sql")
        sql = agents.agente_sql(orq["pergunta_completa"], orq["contexto"], orq["observacoes"])
        usos["sql"] = sql["uso"]
        base.update({k: sql[k] for k in ("colunas", "linhas", "sql", "tentativas_run_sql",
                                          "sql_ok_1a_tentativa", "erros_sql", "motivo_parada")})
        if not sql["ok"]:
            resposta = ("Não consegui montar uma consulta válida para essa pergunta (depois de "
                        f"{sql['tentativas_run_sql']} tentativa(s)). Tente reformular com produto, local e período.")
        else:
            avisar("analista")
            ana = agents.analista(orq["pergunta_completa"], sql)
            usos["analista"] = ana["uso"]
            resposta, base["ressalvas"] = ana["texto"], ana["ressalvas"]

    return {**base, "resposta": resposta, "tempo_s": round(time.perf_counter() - inicio, 1),
            "uso": _somar(*usos.values()), "uso_por_agente": usos}


def conversar() -> None:
    """Modo conversa: guarda o histórico (útil quando o sistema pede esclarecimento)."""
    historico = []
    print("Analista virtual de preços de combustíveis (ANP). Digite 'sair' para encerrar.")
    while True:
        pergunta = input("\nVocê: ").strip()
        if pergunta.lower() in {"sair", "exit", "quit", ""}:
            break
        try:
            res = responder(pergunta, historico)
        except llm.ErroLLM as erro:
            print("Erro:", erro)
            continue
        print("\n" + avaliacao.formatar_resposta(res))
        historico.append({"pergunta": pergunta, "resposta": res["resposta"]})
        historico = historico[-4:]                       # só os últimos turnos (economia)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1 and sys.argv[1] == "--dev":
        avaliacao.rodar_perguntas(responder, ids=set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None,
                                  rotulo="dev_3_agentes")
    elif len(sys.argv) > 1 and sys.argv[1] == "--chat":
        conversar()
    elif len(sys.argv) > 1:
        print(avaliacao.formatar_resposta(responder(" ".join(sys.argv[1:]))))
    else:
        print(__doc__)
