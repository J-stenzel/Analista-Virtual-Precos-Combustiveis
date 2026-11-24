"""
Testes das ferramentas (src/tools.py) — SEM LLM e SEM custo.

Rodar a partir da raiz do projeto, com o venv ativo:
    python tests/testar_tools.py

Blocos:
  1. get_schema / get_metric (conteúdo certo e erro amigável para nome inexistente)
  2. Ataques e consultas proibidas são BLOQUEADOS pelo validate_sql (SQL injection / prompt injection)
  3. Consultas legítimas NÃO são bloqueadas (sem falso alarme) e os avisos de regra aparecem quando devem
  4. Os SQLs de referência do golden set passam no validador (o validador não é rígido demais)
  5. run_sql: LIMIT padrão, truncamento, timeout, bloqueio + auditoria, resultado em JSON
  6. Conexão "jaula" sozinha (defesa em profundidade: barra ataques mesmo sem o validate_sql)
Sai com código 1 se algum teste falhar.
"""
import csv
import json
import sys
import time
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

import tools  # noqa: E402  (import depois de ajustar o sys.path)

falhas = []


def checa(descricao, ok, detalhe=""):
    print(f"  {'OK  ' if ok else 'FALHA'} {descricao} {detalhe}")
    if not ok:
        falhas.append(descricao)


# ---------------------------------------------------------------------------
print("\n1. get_schema / get_metric")
r = tools.get_schema()
checa("get_schema() traz as 6 tabelas", r["ok"] and all(t in r["conteudo"] for t in tools.TABELAS_PERMITIDAS))
r = tools.get_schema(["dim_local"])
checa("get_schema(['dim_local']) inclui a fato e só a relação com dim_local",
      r["ok"] and "fato_precos" in r["conteudo"] and "fato_local" in r["conteudo"] and "fato_posto" not in r["conteudo"])
r = tools.get_schema(["tabela_que_nao_existe"])
checa("get_schema com tabela inexistente -> erro amigável", not r["ok"] and "tabelas_validas" in r)
r = tools.get_metric()
checa("get_metric() devolve o catálogo com 11 métricas (10 + distancia_km, complemento 24/11)",
      r["ok"] and len(yaml.safe_load(r["conteudo"])["catalogo_de_metricas"]) == 11)
r = tools.get_metric(["preco_medio"])
checa("get_metric(['preco_medio']) traz o padrão da média por posto (R13)", r["ok"] and "padrao_media_por_posto" in r["conteudo"])
r = tools.get_metric(["faturamento"])
checa("get_metric com métrica inexistente -> erro + catálogo", not r["ok"] and "catalogo_de_metricas" in r)

# ---------------------------------------------------------------------------
print("\n2. Ataques e consultas proibidas -> BLOQUEADOS")
ataques = {
    "dois comandos (empilhados)":        "SELECT 1; DROP TABLE fato_precos",
    "DROP com comentário e maiúsculas":  "/* inofensivo */ dRoP TABLE dim_tempo",
    "INSERT":                            "INSERT INTO dim_tempo VALUES (1)",
    "UPDATE":                            "UPDATE fato_precos SET valor_venda = 0",
    "DELETE":                            "DELETE FROM fato_precos",
    "ALTER":                             "ALTER TABLE dim_local ADD COLUMN x INT",
    "CREATE TABLE AS SELECT":            "CREATE TABLE copia AS SELECT * FROM dim_local",
    "COPY para arquivo":                 "COPY (SELECT * FROM dim_posto) TO 'C:/Temp/postos.csv'",
    "ATTACH outro banco":                "ATTACH 'C:/Temp/x.duckdb' AS x",
    "SET (religar acesso externo)":      "SET enable_external_access = true",
    "PRAGMA":                            "PRAGMA database_list",
    "INSTALL extensão":                  "INSTALL httpfs",
    "ler arquivo (read_text)":           "SELECT * FROM read_text('C:/Windows/win.ini')",
    "ler CSV (read_csv)":                "SELECT * FROM read_csv('C:/Temp/x.csv')",
    "listar arquivos (glob)":            "SELECT * FROM glob('C:/Users/*')",
    "ler variável de ambiente (getenv)": "SELECT getenv('OPENAI_API_KEY')",
    "configurações internas":            "SELECT * FROM duckdb_settings()",
    "catálogo do sistema":               "SELECT * FROM information_schema.tables",
    "SQL dentro de texto (query())":     "SELECT * FROM query('SELECT * FROM dim_local')",
    "tabela fora do modelo":             "SELECT * FROM tabela_secreta",
    "relógio (R01): CURRENT_DATE":       "SELECT * FROM dim_tempo WHERE data = CURRENT_DATE",
    "relógio (R01): now()":              "SELECT * FROM fato_precos WHERE data > now() - INTERVAL 30 DAY",
    "relógio (R01): current_timestamp":  "SELECT current_timestamp AS agora",
    "relógio (R01): today()":            "SELECT * FROM dim_tempo WHERE data = today()",
    "coluna inexistente (EXPLAIN)":      "SELECT preco FROM fato_precos",
    "sintaxe quebrada":                  "SELEC * FRM fato_precos",
    "vazio":                             "   ",
}
for nome, sql in ataques.items():
    v = tools.validate_sql(sql)
    checa(f"bloqueia: {nome}", not v["valido"], f"-> {v['erros'][0][:70] if v['erros'] else 'NÃO BLOQUEOU'}")

# ---------------------------------------------------------------------------
print("\n3. Consultas legítimas -> NÃO bloqueadas (sem falso alarme)")
legitimas = {
    "ponto e vírgula dentro de texto":     "SELECT 'a;b' AS x",
    "palavra 'DELETE' dentro de texto":    "SELECT razao_social FROM dim_posto WHERE razao_social = 'DELETE LTDA'",
    "EXTRACT(YEAR FROM data)":             "SELECT EXTRACT(YEAR FROM f.data) AS ano, COUNT(*) FROM fato_precos f GROUP BY 1",
    "CTE + JOIN + comentário":             "-- teste\nWITH t AS (SELECT * FROM dim_local) SELECT uf, COUNT(*) FROM t GROUP BY uf",
    "ponto e vírgula no final":            "SELECT COUNT(*) FROM dim_produto;",
}
for nome, sql in legitimas.items():
    v = tools.validate_sql(sql)
    checa(f"aceita: {nome}", v["valido"], f"{v['erros'][:1]}" if v["erros"] else "")

v = tools.validate_sql("SELECT AVG(f.valor_venda) FROM fato_precos f JOIN dim_local l ON l.id_local = f.id_local "
                       "JOIN dim_produto pr ON pr.id_produto = f.id_produto "
                       "WHERE l.municipio = 'CURITIBA' AND pr.produto = 'GASOLINA'")
checa("avisa R12 (município sem UF) e R13 (média direta), mas não bloqueia",
      v["valido"] and any("R12" in a for a in v["avisos"]) and any("R13" in a for a in v["avisos"]))
v = tools.validate_sql("SELECT * FROM dim_bandeira WHERE bandeira ILIKE '%PETRO%'")
checa("avisa ILIKE '%...%' (PETROBRASIL != Petrobras)", v["valido"] and any("ILIKE" in a for a in v["avisos"]))
v = tools.validate_sql("SELECT uf FROM dim_local ORDER BY uf LIMIT 7 OFFSET 20")
checa("avisa OFFSET (paginação — bug achado na rodada depois_2)", v["valido"] and any("OFFSET" in a for a in v["avisos"]))

# ---------------------------------------------------------------------------
print("\n4. SQLs de referência do golden set passam no validador")
with open(RAIZ / "eval" / "golden_set.csv", encoding="utf-8-sig", newline="") as f:
    golden = [g for g in csv.DictReader(f) if g["sql_referencia"].strip()]
sem_erro = [g["id"] for g in golden if tools.validate_sql(g["sql_referencia"])["valido"]]
checa(f"{len(golden)} SQLs de referência sem erro", len(sem_erro) == len(golden),
      f"(falharam: {sorted(set(g['id'] for g in golden) - set(sem_erro))})" if len(sem_erro) != len(golden) else "")
com_aviso = {g["id"]: tools.validate_sql(g["sql_referencia"])["avisos"] for g in golden}
com_aviso = {k: v for k, v in com_aviso.items() if v}
checa("nenhum aviso falso nos SQLs de referência", not com_aviso, f"{com_aviso}" if com_aviso else "")

# ---------------------------------------------------------------------------
print("\n5. run_sql")
sql_mensal = next(g["sql_referencia"] for g in golden if g["id"] == "10")
r = tools.run_sql(sql_mensal)
checa("golden #10 (mês a mês 2025) devolve 12 linhas", r["ok"] and r["total_linhas"] == 12 and not r["truncado"])
checa("acrescenta LIMIT padrão quando falta", r["ok"] and r["sql_executado"].rstrip().endswith(f"LIMIT {tools.LIMITE_PADRAO}"))
checa("resultado vira JSON sem erro", r["ok"] and bool(json.dumps(r, ensure_ascii=False)))
r = tools.run_sql("SELECT uf FROM dim_local ORDER BY uf", limite=5)
checa("limite=5 devolve 5 linhas e marca truncado", r["ok"] and r["total_linhas"] == 5 and r["truncado"])
r = tools.run_sql("SELECT municipio FROM dim_local ORDER BY municipio LIMIT 3")
checa("respeita LIMIT que já existe", r["ok"] and r["total_linhas"] == 3 and r["sql_executado"].count("LIMIT") == 1)
inicio = time.perf_counter()
r = tools.run_sql("SELECT COUNT(*) FROM fato_precos a JOIN fato_precos b ON a.valor_venda > b.valor_venda", timeout_s=1)
duracao = time.perf_counter() - inicio
checa("timeout interrompe consulta pesada", not r["ok"] and r["tipo"] == "timeout" and duracao < 10, f"({duracao:.1f} s)")
tamanho_antes = tools.LOG_PATH.stat().st_size if tools.LOG_PATH.exists() else 0
r = tools.run_sql("SELECT 1; DROP TABLE fato_precos")
checa("run_sql recusa SQL proibido (valida de novo)", not r["ok"] and r["tipo"] == "validacao")
checa("SQL bloqueado registrado em logs/sql_bloqueado.log", tools.LOG_PATH.exists() and tools.LOG_PATH.stat().st_size > tamanho_antes)

# ---------------------------------------------------------------------------
print("\n6. Conexão 'jaula' sozinha (sem passar pelo validate_sql)")
con = tools._conectar()
for nome, sql in {"DROP TABLE": "DROP TABLE dim_tempo",
                  "ler arquivo": "SELECT * FROM read_text('C:/Windows/win.ini')",
                  "religar acesso externo": "SET enable_external_access = true",
                  "exportar arquivo": "COPY (SELECT 1) TO 'C:/Temp/x.csv'"}.items():
    try:
        con.execute(sql).fetchall()
        checa(f"banco recusa sozinho: {nome}", False, "(PASSOU!)")
    except Exception as erro:          # noqa: BLE001 — qualquer recusa do banco serve
        checa(f"banco recusa sozinho: {nome}", True, f"({type(erro).__name__})")
con.close()

print("\n" + ("TODOS OS TESTES PASSARAM ✅" if not falhas else f"{len(falhas)} FALHA(S) ❌: {falhas}"))
sys.exit(1 if falhas else 0)
