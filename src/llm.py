"""
Único ponto de contato com a LLM (OpenAI, Responses API).

Os agentes chamam só `chamar_llm(...)` — não sabem qual provedor está por trás.
Trocar de modelo = mudar o .env. Trocar de provedor = mudar só este arquivo.

Por que a Responses API (e não Chat Completions)?
  Teste de 23/11/2026: na Chat Completions os modelos gpt-6.x só aceitam ferramentas com o raciocínio
  DESLIGADO; na Responses API ferramentas + raciocínio funcionam juntos (melhor para gerar SQL).

Recursos:
  - modelo e esforço de raciocínio por agente (orquestrador / sql / analista), lidos do .env
  - registro de cada chamada em logs/uso_llm.csv: tokens, custo estimado em US$, tempo
  - cache em disco SÓ para desenvolvimento (LLM_CACHE=1 no .env): a mesma chamada não é paga de novo.
    DEIXAR DESLIGADO nas medições oficiais (tempo de resposta e custo precisam ser reais).
  - erros traduzidos para mensagens claras (chave inválida, saldo esgotado, sem conexão...)

Uso pela linha de comando:
    python src/llm.py           -> mostra o gasto acumulado (lê logs/uso_llm.csv; não chama a API)
    python src/llm.py --teste   -> faz 1 chamada mínima de teste (custo < US$ 0,001)
"""
import csv
import datetime
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import openai
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]
load_dotenv(RAIZ / ".env")            # caminho explícito: funciona de qualquer pasta

# Preços em US$ por 1 milhão de tokens: (entrada, entrada em cache, saída)
# Fonte: developers.openai.com/api/docs/pricing — consultado em 23/11/2026 (faixa padrão, contexto curto)
PRECOS = {
    "gpt-6.2-astra": (8.00, 0.40, 40.00),
    "gpt-6.2-sol":   (2.00, 0.10, 10.00),
    "gpt-6.1-terra": (1.00, 0.05, 5.00),
    "gpt-6-luna":    (0.10, 0.01, 0.50),
}

# Modelo e esforço de raciocínio de cada agente (podem ser trocados no .env)
MODELOS = {
    "orquestrador": os.getenv("MODELO_ORQUESTRADOR", "gpt-6.1-terra"),
    "sql":          os.getenv("MODELO_SQL", "gpt-6.2-sol"),
    "analista":     os.getenv("MODELO_ANALISTA", "gpt-6-luna"),
}
ESFORCOS = {
    "orquestrador": os.getenv("ESFORCO_ORQUESTRADOR", "low"),
    "sql":          os.getenv("ESFORCO_SQL", "medium"),
    "analista":     os.getenv("ESFORCO_ANALISTA", "low"),
}

USO_PATH = RAIZ / "logs" / "uso_llm.csv"
CACHE_DIR = RAIZ / ".cache" / "llm"
COLUNAS_USO = ["data_hora", "agente", "modelo", "esforco", "tokens_entrada", "tokens_cache",
               "tokens_saida", "tokens_raciocinio", "custo_usd", "tempo_s", "do_cache"]

_cliente = None


class ErroLLM(Exception):
    """Erro da LLM já traduzido para uma mensagem clara em português."""


def _obter_cliente() -> openai.OpenAI:
    global _cliente
    if _cliente is None:
        if not os.getenv("OPENAI_API_KEY"):
            raise ErroLLM("OPENAI_API_KEY não encontrada: no computador, coloque-a no .env; no Streamlit Cloud, "
                          "em Settings → Secrets do app.")
        _cliente = openai.OpenAI(max_retries=3, timeout=180)   # o SDK repete sozinho em falhas temporárias
    return _cliente


def custo_usd(modelo: str, entrada: int, cache: int, saida: int) -> float | None:
    """Custo estimado da chamada. Tokens em cache custam bem menos que a entrada normal."""
    if modelo not in PRECOS:
        return None
    p_entrada, p_cache, p_saida = PRECOS[modelo]
    return ((entrada - cache) * p_entrada + cache * p_cache + saida * p_saida) / 1_000_000


def _registrar_uso(linha: dict) -> None:
    USO_PATH.parent.mkdir(exist_ok=True)
    novo = not USO_PATH.exists()
    with open(USO_PATH, "a", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS_USO)
        if novo:
            escritor.writeheader()
        escritor.writerow(linha)


def chamar_llm(agente: str, instrucoes: str, entrada: list, ferramentas: list | None = None,
               esforco: str | None = None, max_tokens: int = 16000) -> dict:
    """
    Faz UMA chamada à LLM.

    agente      : "orquestrador", "sql" ou "analista" (define modelo e esforço padrão)
    instrucoes  : prompt de sistema. Deixe-o FIXO (igual em toda chamada) para aproveitar o cache de prompt.
    entrada     : lista de itens no formato da Responses API, ex.: [{"role": "user", "content": "..."}]
                  + itens devolvidos antes (itens_saida) + {"type": "function_call_output", ...}
    ferramentas : definições de função, ex.: {"type": "function", "name": ..., "description": ..., "parameters": {...}}

    Devolve {"texto", "chamadas": [{"call_id", "nome", "argumentos"}], "itens_saida", "incompleto", "uso"}.
    """
    if agente not in MODELOS:
        raise ValueError(f"agente deve ser um de {list(MODELOS)}")
    modelo = MODELOS[agente]
    esforco = esforco or ESFORCOS[agente]
    parametros = {"model": modelo, "instructions": instrucoes, "input": entrada,
                  "reasoning": {"effort": esforco}, "max_output_tokens": max_tokens}
    if ferramentas:
        parametros["tools"] = ferramentas

    # Cache de desenvolvimento: mesma chamada -> mesma resposta, sem pagar de novo
    usar_cache = os.getenv("LLM_CACHE") == "1"
    chave_cache = hashlib.sha256(json.dumps(parametros, sort_keys=True, ensure_ascii=False, default=str)
                                 .encode("utf-8")).hexdigest()
    arquivo_cache = CACHE_DIR / f"{chave_cache}.json"
    if usar_cache and arquivo_cache.exists():
        resultado = json.loads(arquivo_cache.read_text(encoding="utf-8"))
        resultado["uso"] = {**resultado["uso"], "custo_usd": 0.0, "tempo_s": 0.0, "do_cache": True}
        _registrar_uso({"data_hora": datetime.datetime.now().isoformat(timespec="seconds"), "agente": agente,
                        "modelo": modelo, "esforco": esforco, **{k: resultado["uso"][k] for k in
                        ("tokens_entrada", "tokens_cache", "tokens_saida", "tokens_raciocinio")},
                        "custo_usd": 0.0, "tempo_s": 0.0, "do_cache": 1})
        return resultado

    inicio = time.perf_counter()
    try:
        resposta = _obter_cliente().responses.create(**parametros)
    except openai.AuthenticationError as e:
        raise ErroLLM("Chave da OpenAI recusada (inválida ou revogada). Confira o .env.") from e
    except openai.RateLimitError as e:
        if "quota" in str(e).lower():
            raise ErroLLM("Saldo da OpenAI esgotado (insufficient_quota). Adicione créditos no painel.") from e
        raise ErroLLM("Limite de requisições da OpenAI atingido. Espere um pouco e tente de novo.") from e
    except openai.APIConnectionError as e:
        raise ErroLLM("Sem conexão com a OpenAI. Confira a internet.") from e
    except openai.BadRequestError as e:
        raise ErroLLM(f"Requisição recusada pela OpenAI: {str(e)[:400]}") from e
    tempo_s = round(time.perf_counter() - inicio, 2)

    # Separa o texto e os pedidos de ferramenta
    chamadas = []
    for item in resposta.output:
        if item.type == "function_call":
            try:
                argumentos = json.loads(item.arguments or "{}")
            except json.JSONDecodeError:
                argumentos = {"_json_invalido": item.arguments}
            chamadas.append({"call_id": item.call_id, "nome": item.name, "argumentos": argumentos})

    u = resposta.usage
    tokens = {
        "tokens_entrada": u.input_tokens,
        "tokens_cache": (u.input_tokens_details.cached_tokens if u.input_tokens_details else 0) or 0,
        "tokens_saida": u.output_tokens,
        "tokens_raciocinio": (u.output_tokens_details.reasoning_tokens if u.output_tokens_details else 0) or 0,
    }
    custo = custo_usd(modelo, tokens["tokens_entrada"], tokens["tokens_cache"], tokens["tokens_saida"])
    uso = {"modelo": modelo, "esforco": esforco, **tokens,
           "custo_usd": round(custo, 6) if custo is not None else None, "tempo_s": tempo_s, "do_cache": False}

    resultado = {
        "texto": resposta.output_text or "",
        "chamadas": chamadas,
        "itens_saida": [item.model_dump(exclude_none=True) for item in resposta.output],  # devolver na próxima chamada
        "incompleto": (resposta.incomplete_details.reason if resposta.status == "incomplete"
                       and resposta.incomplete_details else None),
        "uso": uso,
    }
    _registrar_uso({"data_hora": datetime.datetime.now().isoformat(timespec="seconds"), "agente": agente,
                    "modelo": modelo, "esforco": esforco, **tokens, "custo_usd": uso["custo_usd"],
                    "tempo_s": tempo_s, "do_cache": 0})
    if usar_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        arquivo_cache.write_text(json.dumps(resultado, ensure_ascii=False, default=str), encoding="utf-8")
    return resultado


def resumo_gasto() -> dict:
    """Soma o que já foi gasto (lê logs/uso_llm.csv, não chama a API)."""
    if not USO_PATH.exists():
        return {"chamadas": 0, "custo_usd": 0.0, "por_modelo": {}}
    total, por_modelo, n = 0.0, {}, 0
    with open(USO_PATH, encoding="utf-8", newline="") as f:
        for linha in csv.DictReader(f):
            n += 1
            valor = float(linha["custo_usd"] or 0)
            total += valor
            por_modelo[linha["modelo"]] = por_modelo.get(linha["modelo"], 0.0) + valor
    return {"chamadas": n, "custo_usd": round(total, 6), "por_modelo": {k: round(v, 6) for k, v in por_modelo.items()}}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--teste" in sys.argv:
        r = chamar_llm("analista", "Responda em português, em no máximo 5 palavras.",
                       [{"role": "user", "content": "Diga apenas: teste ok"}], max_tokens=500)
        print("Resposta:", r["texto"])
        print("Uso:", r["uso"])
    gasto = resumo_gasto()
    print(f"\nGasto acumulado registrado: US$ {gasto['custo_usd']:.6f} em {gasto['chamadas']} chamadas")
    for modelo, valor in gasto["por_modelo"].items():
        print(f"  {modelo:15} US$ {valor:.6f}")
