"""
Ferramentas (tools) que os agentes chamam via tool calling.

    get_schema(tabelas=None)   -> trecho da camada semântica: tabelas, relacionamentos, apelidos, joins proibidos
    get_metric(nomes=None)     -> catálogo de métricas (sem nomes) ou a definição completa das métricas pedidas
    validate_sql(sql)          -> {valido, erros, avisos}   (NÃO executa nada)
    run_sql(sql, limite, timeout_s) -> resultado da consulta, sempre somente leitura

Toda função devolve um dicionário "serializável" em JSON (vai direto para a LLM).
Erros são devolvidos como DADO ({"ok": False, ...}), não como exceção: assim o Agente SQL lê o erro e corrige.

SEGURANÇA — defesa em profundidade (o SQL vindo da LLM é tratado como entrada NÃO confiável):
  1. Menor privilégio: só existem ferramentas de leitura.
  2. Parser oficial do DuckDB: exatamente 1 comando e do tipo SELECT (lista do que é PERMITIDO).
  3. Árvore da consulta (AST): só as 6 tabelas do modelo (ou CTEs); nenhuma função de tabela
     (read_csv, glob, query, duckdb_settings...); funções perigosas (getenv...) e o relógio (R01) bloqueados.
  4. EXPLAIN antes de executar (tabela/coluna/sintaxe), sem rodar a consulta.
  5. Conexão "jaula": read_only + sem acesso a arquivos/rede + configuração travada.
  6. LIMIT padrão + timeout (contra consultas que travam o computador).
  7. Todo SQL bloqueado é registrado em logs/sql_bloqueado.log (auditoria).
"""
import datetime
import decimal
import json
import logging
import os
import re
import threading
import time
from functools import lru_cache
from pathlib import Path

import duckdb
import yaml

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parents[1]
YAML_PATH = RAIZ / "src" / "semantic_layer.yaml"
DB_PATH = Path(os.getenv("DB_PATH") or "data/processed/combustiveis.duckdb")
if not DB_PATH.is_absolute():
    DB_PATH = RAIZ / DB_PATH
LOG_PATH = RAIZ / "logs" / "sql_bloqueado.log"

LIMITE_PADRAO = 100        # linhas devolvidas quando o SQL não tem LIMIT
LIMITE_MAXIMO = 1000       # teto, mesmo que a LLM peça mais
TIMEOUT_PADRAO_S = 30      # segundos

TABELAS_PERMITIDAS = {"fato_precos", "dim_tempo", "dim_local", "dim_produto", "dim_bandeira", "dim_posto"}

# Funções escalares proibidas (lidas na árvore da consulta)
FUNCOES_PROIBIDAS = {"getenv", "current_setting", "current_schema", "current_database", "version",
                     "load_extension", "which_secret"}
# R01: datas relativas vêm da última data da BASE, nunca do relógio
FUNCOES_RELOGIO = {"current_date", "current_time", "current_timestamp", "now", "today",
                   "get_current_time", "get_current_timestamp", "localtimestamp", "localtime",
                   "transaction_timestamp"}
# 2ª linha de defesa por texto (pega o que, por algum motivo, escapar da árvore)
PALAVRAS_PROIBIDAS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|MERGE|COPY|ATTACH|DETACH|PRAGMA|INSTALL|"
    r"LOAD|EXPORT|IMPORT|CHECKPOINT|VACUUM|GRANT|REVOKE)\b", re.IGNORECASE)
NOMES_SISTEMA = re.compile(r"\b(information_schema|pg_catalog|sqlite_master|duckdb_\w+|pragma_\w+)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def carregar_camada() -> dict:
    """Lê o semantic_layer.yaml uma única vez."""
    return yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))


def _yaml(dados) -> str:
    return yaml.safe_dump(dados, allow_unicode=True, sort_keys=False, width=120)


def _conectar() -> duckdb.DuckDBPyConnection:
    """Conexão 'jaula': somente leitura, sem acesso a arquivos/rede e com a configuração travada."""
    return duckdb.connect(str(DB_PATH), read_only=True,
                          config={"enable_external_access": False, "lock_configuration": True})


def _registrar_bloqueio(motivo: str, sql: str) -> None:
    """Auditoria: guarda cada SQL bloqueado (em uma linha) em logs/sql_bloqueado.log."""
    LOG_PATH.parent.mkdir(exist_ok=True)
    logger = logging.getLogger("sql_bloqueado")
    if not logger.handlers:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    logger.info("%s | %s", motivo, " ".join(sql.split())[:1000])


def _sem_textos_e_comentarios(sql: str) -> str:
    """Remove comentários e esvazia textos entre aspas (evita falso alarme com 'DELETE' dentro de um texto)."""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def _percorrer(no, achados: dict) -> None:
    """Percorre a árvore (JSON) da consulta e junta tabelas, funções de tabela, funções e CTEs."""
    if isinstance(no, dict):
        tipo = no.get("type")
        if tipo == "BASE_TABLE":
            achados["tabelas"].add((no.get("schema_name") or "", (no.get("table_name") or "").lower()))
        elif tipo == "TABLE_FUNCTION":
            achados["funcoes_tabela"].add(((no.get("function") or {}).get("function_name") or "?").lower())
        if no.get("class") == "FUNCTION" and no.get("function_name"):
            achados["funcoes"].add(no["function_name"].lower())
        # CURRENT_DATE / current_timestamp SEM parênteses aparecem na árvore como "coluna" de um nome só
        if no.get("class") == "COLUMN_REF" and len(no.get("column_names") or []) == 1:
            achados["funcoes"].add(no["column_names"][0].lower())
        if "cte_map" in no:
            for item in (no["cte_map"] or {}).get("map", []):
                achados["ctes"].add((item.get("key") or "").lower())
        for valor in no.values():
            _percorrer(valor, achados)
    elif isinstance(no, list):
        for valor in no:
            _percorrer(valor, achados)


def _para_json(valor):
    """Converte valores do banco para tipos que o JSON aceita."""
    if isinstance(valor, decimal.Decimal):
        return float(valor)
    if isinstance(valor, (datetime.date, datetime.datetime, datetime.time)):
        return valor.isoformat()
    return valor


# ---------------------------------------------------------------------------
# 1. get_schema
# ---------------------------------------------------------------------------
def get_schema(tabelas: list[str] | None = None) -> dict:
    """Tabelas pedidas (ou todas) + relacionamentos + apelidos + joins proibidos. A fato sempre vem junto."""
    camada = carregar_camada()
    todas = camada["tabelas"]
    if tabelas:
        pedidas = {t.strip().lower() for t in tabelas}
        invalidas = sorted(pedidas - set(todas))
        if invalidas:
            return {"ok": False, "erro": f"Tabela(s) inexistente(s): {invalidas}", "tabelas_validas": list(todas)}
        pedidas.add("fato_precos")                       # toda consulta passa pela fato (modelo estrela)
    else:
        pedidas = set(todas)
    trecho = {
        "tabelas": {nome: dados for nome, dados in todas.items() if nome in pedidas},
        "relacionamentos": [r for r in camada["relacionamentos"] if r["para"].split(".")[0] in pedidas],
        "aliases_padrao": camada["aliases_padrao"],
        "joins_proibidos": camada["joins_proibidos"],
    }
    return {"ok": True, "conteudo": _yaml(trecho)}


# ---------------------------------------------------------------------------
# 2. get_metric
# ---------------------------------------------------------------------------
METRICAS_SIMPLES = {"preco_medio", "preco_minimo", "preco_maximo", "amplitude",
                    "num_postos", "num_coletas", "periodo_da_amostra"}


def get_metric(nomes: list[str] | None = None) -> dict:
    """Sem nomes: catálogo (nome -> descrição). Com nomes: definição completa de cada métrica pedida."""
    camada = carregar_camada()
    metricas = camada["metricas"]
    catalogo = {nome: m["descricao"] for nome, m in metricas.items()}
    if not nomes:
        return {"ok": True, "conteudo": _yaml({"catalogo_de_metricas": catalogo})}
    pedidas = [n.strip().lower() for n in nomes]
    invalidas = [n for n in pedidas if n not in metricas]
    if invalidas:
        return {"ok": False, "erro": f"Métrica(s) inexistente(s): {invalidas}", "catalogo_de_metricas": catalogo}
    trecho = {"metricas": {n: metricas[n] for n in pedidas}}
    usa_media_por_posto = any("preco_posto" in json.dumps(metricas[n], ensure_ascii=False) for n in pedidas)
    if usa_media_por_posto:
        trecho["padrao_media_por_posto"] = camada["padrao_media_por_posto"]   # R13
    if set(pedidas) & METRICAS_SIMPLES:
        trecho["exemplo_metricas_simples"] = camada["exemplo_metricas_simples"]
    return {"ok": True, "conteudo": _yaml(trecho)}


# ---------------------------------------------------------------------------
# 3. validate_sql
# ---------------------------------------------------------------------------
def validate_sql(sql: str) -> dict:
    """Valida SEM executar. Erros bloqueiam; avisos só orientam a correção (heurísticas podem errar)."""
    erros, avisos = [], []
    if not sql or not sql.strip():
        return {"valido": False, "erros": ["SQL vazio."], "avisos": []}

    # Camada 2: parser oficial — exatamente 1 comando, do tipo SELECT
    try:
        comandos = duckdb.extract_statements(sql)
    except duckdb.Error as e:
        return {"valido": False, "erros": [f"Erro de sintaxe: {str(e)[:300]}"], "avisos": []}
    if len(comandos) != 1:
        erros.append(f"Envie exatamente 1 comando (foram encontrados {len(comandos)}).")
    elif comandos[0].type != duckdb.StatementType.SELECT:
        erros.append(f"Somente consultas SELECT são permitidas (recebido: {comandos[0].type.name}).")

    # 2ª linha por texto (sem comentários e sem o conteúdo dos textos entre aspas)
    limpo = _sem_textos_e_comentarios(sql)
    if m := PALAVRAS_PROIBIDAS.search(limpo):
        erros.append(f"Comando proibido: {m.group(1).upper()} (o acesso é somente leitura).")
    if m := NOMES_SISTEMA.search(limpo):
        erros.append(f"Tabelas/funções internas do banco não são permitidas: {m.group(1)}.")
    if erros:
        return {"valido": False, "erros": erros, "avisos": []}

    con = _conectar()
    try:
        # Camada 3: árvore da consulta (tabelas, funções de tabela, funções)
        arvore = json.loads(con.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0])
        if arvore.get("error"):
            erros.append(f"Erro de sintaxe: {arvore.get('error_message', '')[:300]}")
        else:
            achados = {"tabelas": set(), "funcoes_tabela": set(), "funcoes": set(), "ctes": set()}
            _percorrer(arvore, achados)
            for esquema, tabela in sorted(achados["tabelas"]):
                if esquema or (tabela not in TABELAS_PERMITIDAS and tabela not in achados["ctes"]):
                    erros.append(f"Tabela não permitida: {(esquema + '.') if esquema else ''}{tabela}. "
                                 f"Use apenas: {sorted(TABELAS_PERMITIDAS)}.")
            for funcao in sorted(achados["funcoes_tabela"]):
                erros.append(f"Função de tabela não permitida: {funcao}() (leitura de arquivos/sistema).")
            for funcao in sorted(achados["funcoes"] & FUNCOES_PROIBIDAS):
                erros.append(f"Função não permitida: {funcao}().")
            for funcao in sorted(achados["funcoes"] & FUNCOES_RELOGIO):
                erros.append(f"R01: não use {funcao} (data do relógio). Datas relativas vêm de MAX(f.data) da base.")
        # Camada 4: EXPLAIN — confere tabelas, colunas e tipos sem executar a consulta
        if not erros:
            try:
                con.execute("EXPLAIN " + sql)
            except duckdb.Error as e:
                erros.append(f"{type(e).__name__}: {str(e)[:400]}")
    finally:
        con.close()

    # Avisos de regras de negócio (não bloqueiam)
    minusculo = limpo.lower()
    if re.search(r"\bmunicipio\s*(=|in\b|like\b|ilike\b)", minusculo) and not re.search(r"\buf\s*(=|in\b)", minusculo):
        avisos.append("R12: filtro de município sem UF (nomes se repetem entre estados).")
    if re.search(r"avg\s*\(\s*(\w+\.)?valor_venda", minusculo) and "preco_posto" not in minusculo:
        avisos.append("R13: preço médio deve ser média POR POSTO (CTE por_posto), não AVG(valor_venda) direto.")
    if re.search(r"\bi?like\s+'%", sql, re.IGNORECASE):
        avisos.append("Filtro com LIKE/ILIKE '%...%': prefira '=' com o valor exato da base (ver sinonimos).")
    if "valor_venda" in minusculo and not re.search(r"\b(produto|id_produto|tipo_combustivel)\b", minusculo):
        avisos.append("R11: consulta de preço sem filtro/agrupamento por produto (não misture produtos nem GNV).")
    if re.search(r"\boffset\b", minusculo):
        avisos.append("OFFSET: não pagine o resultado — o usuário recebe a tabela completa da consulta principal.")

    return {"valido": not erros, "erros": erros, "avisos": avisos}


# ---------------------------------------------------------------------------
# 4. run_sql
# ---------------------------------------------------------------------------
def run_sql(sql: str, limite: int = LIMITE_PADRAO, timeout_s: float = TIMEOUT_PADRAO_S) -> dict:
    """Executa um SELECT validado, em modo somente leitura, com LIMIT padrão e timeout."""
    limite = max(1, min(int(limite), LIMITE_MAXIMO))

    validacao = validate_sql(sql)                         # valida de novo: não confia em quem chamou
    if not validacao["valido"]:
        _registrar_bloqueio("; ".join(validacao["erros"]), sql)
        return {"ok": False, "tipo": "validacao", "erro": " | ".join(validacao["erros"]),
                "avisos": validacao["avisos"]}

    # LIMIT padrão: acrescenta no fim se a consulta não terminar com LIMIT (nova linha evita cair num comentário)
    sql_executado = sql.strip().rstrip(";").rstrip()
    if not re.search(r"\blimit\s+\d+(\s+offset\s+\d+)?\s*$", _sem_textos_e_comentarios(sql_executado),
                     re.IGNORECASE):
        sql_executado += f"\nLIMIT {limite}"

    con = _conectar()
    cronometro = threading.Timer(timeout_s, con.interrupt)   # timeout: interrompe a consulta
    inicio = time.perf_counter()
    try:
        cronometro.start()
        cursor = con.execute(sql_executado)
        colunas = [c[0] for c in cursor.description]
        linhas = [[_para_json(v) for v in linha] for linha in cursor.fetchmany(limite)]
    except duckdb.InterruptException:
        return {"ok": False, "tipo": "timeout",
                "erro": f"A consulta passou de {timeout_s:g} s e foi interrompida. Simplifique ou filtre mais."}
    except duckdb.Error as e:
        return {"ok": False, "tipo": "execucao", "erro": f"{type(e).__name__}: {str(e)[:500]}"}
    finally:
        cronometro.cancel()
        con.close()

    return {
        "ok": True,
        "colunas": colunas,
        "linhas": linhas,
        "total_linhas": len(linhas),
        "truncado": len(linhas) >= limite,               # True = pode haver mais linhas além do limite
        "limite": limite,
        "tempo_ms": round((time.perf_counter() - inicio) * 1000),
        "sql_executado": sql_executado,                   # mostrado ao usuário (transparência)
        "avisos": validacao["avisos"],
    }
