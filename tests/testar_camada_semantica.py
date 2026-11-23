"""
Testes da camada semântica (src/semantic_layer.yaml) contra o banco DuckDB.

Rodar a partir da raiz do projeto, com o venv ativo:
    python tests/testar_camada_semantica.py

O que é testado (4 blocos):
  1. O YAML abre sem erro e tem as 6 seções obrigatórias.
  2. Todo SQL completo do YAML (exemplos de métricas e de regras) roda no banco.
  3. Todo valor-alvo dos sinônimos existe de verdade no banco
     (senão o filtro "WHERE produto = 'X'" volta vazio sem dar erro).
  4. As métricas, recalculadas em pandas a partir das LINHAS BRUTAS (outro caminho,
     sem AVG/GROUP BY no SQL), dão o mesmo número que o SQL do YAML.

Rode de novo SEMPRE que mexer no YAML (ex.: nas correções da Etapa 4).
Sai com código 1 se algum teste falhar.
"""
import re
import sys
from pathlib import Path

import duckdb
import yaml

sys.stdout.reconfigure(encoding="utf-8")   # evita erro de acento/emoji no terminal do Windows

RAIZ = Path(__file__).resolve().parents[1]
YAML_PATH = RAIZ / "src" / "semantic_layer.yaml"
DB_PATH = RAIZ / "data" / "processed" / "combustiveis.duckdb"

camada = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
con = duckdb.connect(str(DB_PATH), read_only=True)   # somente leitura

falhas = []


def checa(descricao, ok, detalhe=""):
    """Registra e imprime o resultado de uma verificação."""
    print(f"  {'OK  ' if ok else 'FALHA'} {descricao} {detalhe}")
    if not ok:
        falhas.append(descricao)


def sql_executavel(sql):
    """True se o texto é uma consulta completa (não um trecho nem um modelo com <...>)."""
    sem_comentarios = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--")).strip()
    return sem_comentarios.upper().startswith(("SELECT", "WITH")) and not re.search(r"<[^>]+>", sql)


# ---------------------------------------------------------------------------
print("\n1. Estrutura do YAML")
for secao in ["projeto", "tabelas", "relacionamentos", "metricas", "sinonimos", "regras_de_negocio"]:
    checa(f"seção '{secao}' existe", secao in camada)
checa("6 tabelas descritas", len(camada["tabelas"]) == 6)
ids = [r["id"] for r in camada["regras_de_negocio"]]
checa("ids das regras sem repetição", len(ids) == len(set(ids)), str(ids))

# ---------------------------------------------------------------------------
print("\n2. Todo SQL completo do YAML roda no banco")
consultas = {}
for nome, m in camada["metricas"].items():
    if "exemplo" in m:
        consultas[f"metrica {nome}"] = m["exemplo"]["sql"]
consultas["exemplo_metricas_simples"] = camada["exemplo_metricas_simples"]["sql"]
for r in camada["regras_de_negocio"]:
    if "sql" in r:
        consultas[f"regra {r['id']}"] = r["sql"]
    if "exemplo" in r:
        consultas[f"regra {r['id']} exemplo"] = r["exemplo"]["sql"]
for nome, sql in consultas.items():
    if not sql_executavel(sql):
        continue                      # trecho de expressão ou modelo para a LLM preencher
    try:
        linhas = len(con.execute(sql).fetchall())
        checa(nome, linhas > 0, f"({linhas} linhas)")
    except Exception as erro:          # noqa: BLE001 — queremos registrar qualquer erro de SQL
        checa(nome, False, f"ERRO: {erro}")

# ---------------------------------------------------------------------------
print("\n3. Valores-alvo dos sinônimos existem no banco")
s = camada["sinonimos"]


def existe(sql, *parametros):
    return con.execute(sql, list(parametros)).fetchone()[0] > 0


for v in s["produtos"]:
    checa(f"produto {v}", existe("SELECT COUNT(*) FROM dim_produto WHERE produto = ?", v))
for v in s["tipos_combustivel"]:
    checa(f"tipo {v}", existe("SELECT COUNT(*) FROM dim_produto WHERE tipo_combustivel = ?", v))
for v in s["bandeiras"]:
    checa(f"bandeira {v}", existe("SELECT COUNT(*) FROM dim_bandeira WHERE bandeira = ?", v))
checa("existe bandeira branca", existe("SELECT COUNT(*) FROM dim_bandeira WHERE eh_bandeira_branca"))
for v in s["regioes"]:
    checa(f"região {v}", existe("SELECT COUNT(*) FROM dim_local WHERE regiao_sigla = ?", v))
ufs_banco = con.execute("SELECT COUNT(DISTINCT uf) FROM dim_local").fetchone()[0]
checa("todas as UFs do banco estão nos sinônimos", len(s["ufs"]) == ufs_banco, f"({len(s['ufs'])} de {ufs_banco})")
for v in s["ufs"]:
    checa(f"UF {v}", existe("SELECT COUNT(*) FROM dim_local WHERE uf = ?", v))
for chave in s["municipios_apelidos"]:
    municipio, uf = chave.split("/")
    checa(f"município {chave}",
          existe("SELECT COUNT(*) FROM dim_local WHERE municipio = ? AND uf = ?", municipio, uf))

# ---------------------------------------------------------------------------
print("\n4. Métricas conferidas em pandas (linhas brutas) x SQL do YAML")
M = camada["metricas"]


def brutas(where):
    """Linhas da fato SEM agregação, já com os atributos das dimensões."""
    return con.execute(f"""
        SELECT f.cnpj, f.data, f.valor_venda::DOUBLE AS v, pr.produto, l.uf, l.regiao_nome,
               b.eh_bandeira_branca AS branca, t.ano
        FROM fato_precos f
        JOIN dim_produto pr ON pr.id_produto = f.id_produto
        JOIN dim_local l    ON l.id_local    = f.id_local
        JOIN dim_bandeira b ON b.id_bandeira = f.id_bandeira
        JOIN dim_tempo t    ON t.data        = f.data
        WHERE {where}""").df()


def compara(descricao, valor_yaml, valor_pandas, tolerancia=0.0015):
    ok = abs(float(valor_yaml) - float(valor_pandas)) <= tolerancia
    checa(descricao, ok, f"(yaml={float(valor_yaml):.3f} pandas={float(valor_pandas):.3f})")


# 4a) métricas simples — gasolina em Porto Alegre, mai/2026
y = con.execute(camada["exemplo_metricas_simples"]["sql"]).df().iloc[0]
b = brutas("pr.produto = 'GASOLINA' AND l.municipio = 'PORTO ALEGRE' AND l.uf = 'RS' AND t.ano_mes = '2026-05'")
compara("preco_medio = média por posto", y.preco_medio, b.groupby("cnpj").v.mean().mean())
compara("preco_minimo", y.preco_minimo, b.v.min())
compara("preco_maximo", y.preco_maximo, b.v.max())
compara("amplitude", y.amplitude, b.v.max() - b.v.min())
compara("num_postos", y.num_postos, b.cnpj.nunique(), 0)
compara("num_coletas", y.num_coletas, len(b), 0)

# 4b) variação % — etanol 2024 x 2025 por região
y = con.execute(M["variacao_percentual"]["exemplo"]["sql"]).df().set_index("regiao_nome")
b = brutas("pr.produto = 'ETANOL' AND t.ano IN (2024, 2025)")
media = b.groupby(["regiao_nome", "ano", "cnpj"]).v.mean().groupby(["regiao_nome", "ano"]).mean().unstack()
variacao = (media[2025] / media[2024] - 1) * 100
for regiao in y.index:
    compara(f"variacao_percentual {regiao}", y.loc[regiao, "variacao_pct"], variacao[regiao], 0.006)

# 4c) diferença bandeira x branca — diesel S10 no Sul, 2025
y = con.execute(M["diferenca_bandeira_vs_branca"]["exemplo"]["sql"]).df().set_index("uf")
b = brutas("pr.produto = 'DIESEL S10' AND t.ano = 2025 AND l.regiao_sigla = 'S'")
m = b.groupby(["uf", "branca", "cnpj"]).v.mean().groupby(["uf", "branca"]).mean().unstack()
for uf in y.index:
    compara(f"diferenca_bandeira_vs_branca {uf}", y.loc[uf, "diferenca"], m.loc[uf, False] - m.loc[uf, True])

# 4d) razão etanol/gasolina — Campinas, 2º tri/2026 (pares posto + data)
y = con.execute(M["razao_etanol_gasolina"]["exemplo"]["sql"]).df()
b = brutas("pr.produto IN ('ETANOL', 'GASOLINA') AND l.municipio = 'CAMPINAS' AND l.uf = 'SP' "
           "AND f.data BETWEEN DATE '2026-04-01' AND DATE '2026-06-30'")
pares = b.pivot_table(index=["cnpj", "data"], columns="produto", values="v").dropna()
pares["razao"] = pares.ETANOL / pares.GASOLINA
compara("razao: nº de pares posto+data", len(y), len(pares), 0)
compara("razao: nº de pares em que o etanol compensa", y.etanol_compensa.sum(), (pares.razao <= 0.70).sum(), 0)
compara("razao: menor razão", y.razao.min(), pares.razao.min())

# ---------------------------------------------------------------------------
con.close()
print("\n" + ("TODOS OS TESTES PASSARAM ✅" if not falhas else f"{len(falhas)} FALHA(S) ❌: {falhas}"))
sys.exit(1 if falhas else 0)
