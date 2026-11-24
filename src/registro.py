"""
Registro das perguntas feitas no app (etapas 5.10/5.11) — uma linha por pergunta numa PLANILHA GOOGLE.

Para que serve: acompanhar o uso do app online (quantas perguntas, de que tipo, custo, tempo, se houve erro).

Destino:
  1) Planilha Google (gspread + conta de serviço): credencial em st.secrets["gcp_service_account"] e o link
     da planilha em st.secrets["registro"]["planilha_url"] — os dois só nos Secrets/.streamlit/secrets.toml,
     NUNCA no código nem no GitHub. A planilha precisa estar compartilhada com o e-mail da conta de serviço.
  2) Reserva: sem credencial (ou se o Google falhar), a linha vai para logs/perguntas.csv (fora do GitHub).
  O registro roda em SEGUNDO PLANO (thread): o usuário não espera, e uma falha aqui nunca derruba o app.

O que é guardado (decisões do aluno, 24/11 — LGPD: só o necessário, com aviso no app):
  data/hora (Brasília), id aleatório da sessão, IP, navegador, sistema, fuso, idioma, localização
  (arredondada para 2 casas ≈ 1 km quando vem do navegador; o CEP quando o usuário digitou um CEP),
  pergunta, tipo de resposta, pergunta interpretada, nº de linhas, SQL válido na 1ª, custo, tempo, erro.
  NÃO guarda nome da máquina nem geolocalização pelo IP.
"""
from __future__ import annotations

import csv
import datetime
import re
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CSV_RESERVA = RAIZ / "logs" / "perguntas.csv"
FUSO_BRASILIA = datetime.timezone(datetime.timedelta(hours=-3))
COLUNAS = ["data_hora", "sessao", "ip", "navegador", "sistema", "fuso", "idioma", "localizacao", "pergunta",
           "classe", "pergunta_interpretada", "linhas", "sql_ok_1a_tentativa", "custo_usd", "tempo_s", "erro"]

_trava = threading.Lock()          # uma escrita por vez (planilha e CSV)
_aba = None                        # aba da planilha, aberta uma única vez por processo
_motivo_reserva = None             # por que a planilha não está sendo usada (para mostrar no app)


def navegador_e_sistema(user_agent: str | None) -> tuple[str, str]:
    """'Chrome / Windows' a partir do User-Agent (sem guardar o texto completo, que identifica mais)."""
    ua = user_agent or ""
    navegador = next((nome for padrao, nome in [(r"Edg/", "Edge"), (r"OPR/|Opera", "Opera"), (r"Firefox/", "Firefox"),
                      (r"Chrome/", "Chrome"), (r"Safari/", "Safari")] if re.search(padrao, ua)), "outro")
    sistema = next((nome for padrao, nome in [(r"Android", "Android"), (r"iPhone|iPad", "iOS"), (r"Windows", "Windows"),
                    (r"Mac OS", "macOS"), (r"Linux", "Linux")] if re.search(padrao, ua)), "outro")
    return navegador, sistema


def localizacao_para_registro(local: dict | None) -> str:
    """Mínimo necessário: CEP digitado -> o CEP; navegador -> coordenada arredondada (2 casas ≈ 1 km)."""
    if not local:
        return ""
    if str(local.get("fonte", "")).startswith("CEP"):
        return local["fonte"]
    return f"{float(local['lat']):.2f}, {float(local['lon']):.2f}"


def montar_linha(contexto: dict, pergunta: str, res: dict | None = None, erro: str = "") -> dict:
    """contexto = {"sessao", "ip", "user_agent", "fuso", "idioma", "localizacao"} (vem do app)."""
    navegador, sistema = navegador_e_sistema(contexto.get("user_agent"))
    res = res or {}
    return {
        "data_hora": datetime.datetime.now(FUSO_BRASILIA).strftime("%d/%m/%Y %H:%M:%S"),
        "sessao": contexto.get("sessao", ""), "ip": contexto.get("ip") or "",
        "navegador": navegador, "sistema": sistema,
        "fuso": contexto.get("fuso") or "", "idioma": contexto.get("idioma") or "",
        "localizacao": localizacao_para_registro(contexto.get("localizacao")),
        "pergunta": pergunta, "classe": res.get("classe", "ERRO" if erro else ""),
        "pergunta_interpretada": res.get("pergunta_completa") or "",
        "linhas": len(res.get("linhas") or []),
        "sql_ok_1a_tentativa": "" if res.get("sql_ok_1a_tentativa") is None else ("sim" if res["sql_ok_1a_tentativa"] else "não"),
        "custo_usd": round((res.get("uso") or {}).get("custo_usd") or 0, 4), "tempo_s": res.get("tempo_s", ""),
        "erro": erro,
    }


def _abrir_aba(credenciais: dict, planilha_url: str):
    """Abre (uma vez) a 1ª aba da planilha e escreve o cabeçalho se ela estiver vazia."""
    global _aba
    if _aba is None:
        import gspread                                   # só importa se houver credencial
        cliente = gspread.service_account_from_dict(dict(credenciais))
        aba = cliente.open_by_url(planilha_url).sheet1
        if not aba.row_values(1):
            aba.append_row(COLUNAS, value_input_option="RAW")
        _aba = aba
    return _aba


def _gravar_csv(linha: dict) -> None:
    CSV_RESERVA.parent.mkdir(exist_ok=True)
    novo = not CSV_RESERVA.exists()
    with open(CSV_RESERVA, "a", encoding="utf-8-sig", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS)
        if novo:
            escritor.writeheader()
        escritor.writerow(linha)


def _gravar(linha: dict, credenciais: dict | None, planilha_url: str | None) -> None:
    global _motivo_reserva
    with _trava:
        if credenciais and planilha_url:
            try:
                _abrir_aba(credenciais, planilha_url).append_row([linha[c] for c in COLUNAS], value_input_option="RAW")
                _motivo_reserva = None
                return
            except Exception as erro:                    # sem acesso, sem internet, cota... -> reserva em CSV
                _motivo_reserva = f"planilha indisponível ({type(erro).__name__})"
        else:
            _motivo_reserva = "sem credencial da planilha"
        _gravar_csv(linha)


def registrar(linha: dict, credenciais: dict | None = None, planilha_url: str | None = None) -> None:
    """Grava em SEGUNDO PLANO (o usuário não espera o Google responder)."""
    threading.Thread(target=_gravar, args=(linha, credenciais, planilha_url), daemon=True).start()


def situacao() -> str:
    """Texto curto para o app/testes: para onde o registro está indo."""
    return "planilha Google" if _aba is not None and _motivo_reserva is None else f"CSV local ({_motivo_reserva or 'ainda sem registro'})"
