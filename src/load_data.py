"""
Etapa 2 — Carga, limpeza, modelagem (estrela) e testes de qualidade.

Entrada : data/raw/*.csv  (ANP — Série Histórica de Preços de Combustíveis, semestral)
Saída   : data/processed/combustiveis.duckdb  com o modelo estrela:

                 dim_tempo
                     │
    dim_local ── fato_precos ── dim_produto
                     │
       dim_posto ────┴──── dim_bandeira

Como rodar (na pasta do projeto):
    python src/load_data.py
    python src/load_data.py --db caminho/outro.duckdb   (opcional)

Etapas do script (cada uma é uma função):
    1. ler_bruto()        -> stg_bruto       (tudo como texto, 1 linha por linha do CSV)
    2. limpar()           -> stg_limpo       (tipos, padronizações, linhas vazias, duplicatas)
    3. criar_dimensoes()  -> dim_*           (chaves substitutas inteiras)
    4. criar_fato()       -> fato_precos
    5. testes_qualidade() -> relatório + falha se algum teste CRÍTICO quebrar
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[1]
RAW = RAIZ / "data" / "raw"
DB_PADRAO = RAIZ / "data" / "processed" / "combustiveis.duckdb"
RELATORIO = RAIZ / "docs" / "qualidade_dados.md"

# ---------------------------------------------------------------------------
# Regras de padronização (decisões de negócio documentadas em docs/exploracao.md)
# ---------------------------------------------------------------------------
# A mesma distribuidora aparece com nomes diferentes ao longo do tempo.
BANDEIRA_PADRAO = {
    "PETROBRAS DISTRIBUIDORA S.A.": "VIBRA",   # virou Vibra Energia em 2021
    "VIBRA ENERGIA": "VIBRA",                  # encurtado para Vibra em 2023
    "ALESAT": "ALE",                           # renomeada em 2024
    "FEDERAL": "FEDERAL ENERGIA",              # renomeada em 2021
    "TOTAL BRASIL": "TOTALENERGIES",           # renomeada em 2021
}

REGIAO_NOME = {"N": "Norte", "NE": "Nordeste", "CO": "Centro-Oeste", "SE": "Sudeste", "S": "Sul"}

TIPO_COMBUSTIVEL = {
    "GASOLINA": "GASOLINA",
    "GASOLINA ADITIVADA": "GASOLINA",
    "ETANOL": "ETANOL",
    "DIESEL": "DIESEL",
    "DIESEL S10": "DIESEL",
    "GNV": "GNV",
}

TABELAS_FINAIS = ["fato_precos", "dim_tempo", "dim_local", "dim_produto", "dim_bandeira", "dim_posto"]

# Faixa de preço plausível (R$ por litro ou m³). Fora disso = suspeito.
PRECO_MIN, PRECO_MAX = 0.5, 20.0


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def detectar_encoding(caminho: Path) -> str:
    """A ANP mistura UTF-8 e latin-1. Tenta UTF-8; se não decodificar, é latin-1."""
    with open(caminho, "rb") as f:
        amostra = f.read(5_000_000)
    try:
        amostra.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def mapa_sql(dicionario: dict[str, str]) -> str:
    """Transforma um dict Python em um MAP do DuckDB para usar dentro do SQL."""
    pares = ", ".join(f"'{k}': '{v}'" for k, v in dicionario.items())
    return "MAP {" + pares + "}"


# ---------------------------------------------------------------------------
# 1. Leitura
# ---------------------------------------------------------------------------
def ler_bruto(con: duckdb.DuckDBPyConnection) -> None:
    """Lê todos os CSVs como TEXTO. Converter tipos só depois evita erros silenciosos."""
    arquivos = sorted(RAW.glob("*.csv"))
    if not arquivos:
        sys.exit(f"Nenhum CSV encontrado em {RAW}")
    partes = []
    for arq in arquivos:
        enc = detectar_encoding(arq)
        periodo = arq.stem.split("_")[-1]  # ex.: 2025.01
        log(f"lendo {arq.name} (encoding={enc})")
        partes.append(
            f"""SELECT '{periodo}' AS arquivo_origem, *
                FROM read_csv('{arq.as_posix()}', delim=';', header=true,
                              all_varchar=true, encoding='{enc}')"""
        )
    con.execute("CREATE OR REPLACE TABLE stg_bruto AS " + " UNION ALL BY NAME ".join(partes))


# ---------------------------------------------------------------------------
# 2. Limpeza
# ---------------------------------------------------------------------------
def limpar(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE OR REPLACE TABLE stg_limpo AS
        WITH base AS (
            SELECT
                arquivo_origem,
                UPPER(TRIM("Regiao - Sigla"))                         AS regiao_sigla,
                UPPER(TRIM("Estado - Sigla"))                         AS uf,
                UPPER(TRIM("Municipio"))                              AS municipio,
                UPPER(TRIM("Revenda"))                                AS razao_social,
                regexp_replace("CNPJ da Revenda", '[^0-9]', '', 'g')  AS cnpj,        -- só dígitos
                UPPER(TRIM("Bairro"))                                 AS bairro,
                TRIM("Cep")                                           AS cep,
                UPPER(TRIM("Produto"))                                AS produto,
                strptime(TRIM("Data da Coleta"), '%d/%m/%Y')::DATE    AS data_coleta,
                CAST(REPLACE(TRIM("Valor de Venda"), ',', '.') AS DECIMAL(10,3)) AS valor_venda,
                REPLACE(TRIM("Unidade de Medida"), 'm3', 'm³')        AS unidade,     -- padroniza GNV
                UPPER(TRIM("Bandeira"))                               AS bandeira_original
                -- "Valor de Compra" e endereço detalhado foram descartados de propósito
            FROM stg_bruto
            WHERE "Produto" IS NOT NULL AND TRIM("Produto") <> ''     -- remove linhas vazias
        )
        SELECT *,
               COALESCE({mapa_sql(BANDEIRA_PADRAO)}[bandeira_original], bandeira_original) AS bandeira
        FROM base
    """)

    # Duplicatas no grão (posto × produto × data). Se houver mais de um preço para a
    # mesma chave, ficamos com a MÉDIA e registramos quantas eram (transparência).
    con.execute("""
        CREATE OR REPLACE TABLE stg_limpo AS
        SELECT
            cnpj, produto, data_coleta,
            ANY_VALUE(arquivo_origem)     AS arquivo_origem,
            ANY_VALUE(regiao_sigla)       AS regiao_sigla,
            ANY_VALUE(uf)                 AS uf,
            ANY_VALUE(municipio)          AS municipio,
            ANY_VALUE(razao_social)       AS razao_social,
            ANY_VALUE(bairro)             AS bairro,
            ANY_VALUE(cep)                AS cep,
            ANY_VALUE(unidade)            AS unidade,
            ANY_VALUE(bandeira_original)  AS bandeira_original,
            ANY_VALUE(bandeira)           AS bandeira,
            CAST(AVG(valor_venda) AS DECIMAL(10,3)) AS valor_venda,
            COUNT(*)                      AS qtd_registros_origem
        FROM stg_limpo
        GROUP BY cnpj, produto, data_coleta
    """)


# ---------------------------------------------------------------------------
# 3. Dimensões
# ---------------------------------------------------------------------------
def criar_dimensoes(con: duckdb.DuckDBPyConnection) -> None:
    # dim_local: hierarquia Região > UF > Município
    con.execute(f"""
        CREATE OR REPLACE TABLE dim_local AS
        SELECT ROW_NUMBER() OVER (ORDER BY regiao_sigla, uf, municipio)::INTEGER AS id_local,
               regiao_sigla,
               {mapa_sql(REGIAO_NOME)}[regiao_sigla] AS regiao_nome,
               uf, municipio
        FROM (SELECT DISTINCT regiao_sigla, uf, municipio FROM stg_limpo)
    """)

    # dim_tempo: um dia por linha, do 1º ao último dia coletado (inclui dias sem coleta)
    con.execute("""
        CREATE OR REPLACE TABLE dim_tempo AS
        SELECT d::DATE                                      AS data,
               YEAR(d)::INTEGER                             AS ano,
               CASE WHEN MONTH(d) <= 6 THEN 1 ELSE 2 END    AS semestre,
               QUARTER(d)::INTEGER                          AS trimestre,
               MONTH(d)::INTEGER                            AS mes,
               strftime(d, '%Y-%m')                         AS ano_mes,
               WEEKOFYEAR(d)::INTEGER                       AS semana_iso,
               ISODOW(d)::INTEGER                           AS dia_semana_num,   -- 1=segunda
               CASE ISODOW(d) WHEN 1 THEN 'segunda' WHEN 2 THEN 'terça' WHEN 3 THEN 'quarta'
                              WHEN 4 THEN 'quinta' WHEN 5 THEN 'sexta' WHEN 6 THEN 'sábado'
                              ELSE 'domingo' END            AS dia_semana
        FROM generate_series(
                 (SELECT MIN(data_coleta) FROM stg_limpo)::TIMESTAMP,
                 (SELECT MAX(data_coleta) FROM stg_limpo)::TIMESTAMP,
                 INTERVAL 1 DAY) AS t(d)
    """)

    # dim_produto
    con.execute(f"""
        CREATE OR REPLACE TABLE dim_produto AS
        SELECT ROW_NUMBER() OVER (ORDER BY produto)::INTEGER AS id_produto,
               produto,
               {mapa_sql(TIPO_COMBUSTIVEL)}[produto] AS tipo_combustivel,
               unidade
        FROM (SELECT produto, ANY_VALUE(unidade) AS unidade FROM stg_limpo GROUP BY produto)
    """)

    # dim_bandeira (já padronizada) + flag de bandeira branca
    con.execute("""
        CREATE OR REPLACE TABLE dim_bandeira AS
        SELECT ROW_NUMBER() OVER (ORDER BY bandeira)::INTEGER AS id_bandeira,
               bandeira,
               (bandeira = 'BRANCA') AS eh_bandeira_branca,
               nomes_originais
        FROM (SELECT bandeira, string_agg(DISTINCT bandeira_original, ' | ') AS nomes_originais
              FROM stg_limpo GROUP BY bandeira)
    """)

    # dim_posto: dados cadastrais MAIS RECENTES de cada CNPJ
    con.execute("""
        CREATE OR REPLACE TABLE dim_posto AS
        SELECT cnpj,
               arg_max(razao_social, data_coleta) AS razao_social,
               arg_max(bairro, data_coleta)       AS bairro,
               arg_max(cep, data_coleta)          AS cep,
               MIN(data_coleta)                   AS primeira_coleta,
               MAX(data_coleta)                   AS ultima_coleta
        FROM stg_limpo
        GROUP BY cnpj
    """)


# ---------------------------------------------------------------------------
# 4. Fato
# ---------------------------------------------------------------------------
def criar_fato(con: duckdb.DuckDBPyConnection) -> None:
    """Grão: 1 linha = preço de 1 produto, em 1 posto, em 1 data de coleta.
    Local e bandeira ficam na FATO porque podem mudar ao longo do tempo para o mesmo posto."""
    con.execute("""
        CREATE OR REPLACE TABLE fato_precos AS
        SELECT s.data_coleta AS data,
               s.cnpj,
               l.id_local,
               p.id_produto,
               b.id_bandeira,
               s.valor_venda,
               s.qtd_registros_origem,
               s.arquivo_origem
        FROM stg_limpo s
        JOIN dim_local    l USING (regiao_sigla, uf, municipio)
        JOIN dim_produto  p USING (produto)
        JOIN dim_bandeira b USING (bandeira)
        ORDER BY s.data_coleta
    """)


# ---------------------------------------------------------------------------
# 5. Testes de qualidade
# ---------------------------------------------------------------------------
TESTES = [
    # (nome, criticidade, SQL que retorna a QUANTIDADE de problemas — esperado 0)
    ("Linhas vazias removidas (informativo)", "INFO",
     "SELECT COUNT(*) FROM stg_bruto WHERE \"Produto\" IS NULL OR TRIM(\"Produto\") = ''"),
    ("Registros de origem agregados por duplicidade (informativo)", "INFO",
     "SELECT COALESCE(SUM(qtd_registros_origem - 1), 0) FROM fato_precos"),
    ("Nulos em colunas-chave da fato", "CRITICO",
     """SELECT COUNT(*) FROM fato_precos
        WHERE data IS NULL OR cnpj IS NULL OR id_local IS NULL OR id_produto IS NULL
           OR id_bandeira IS NULL OR valor_venda IS NULL"""),
    ("Duplicatas no grão (data, cnpj, produto)", "CRITICO",
     "SELECT COUNT(*) FROM (SELECT data, cnpj, id_produto FROM fato_precos GROUP BY ALL HAVING COUNT(*) > 1)"),
    ("CNPJ com tamanho diferente de 14 dígitos", "CRITICO",
     "SELECT COUNT(*) FROM dim_posto WHERE length(cnpj) <> 14"),
    ("Chave órfã: fato.data sem dim_tempo", "CRITICO",
     "SELECT COUNT(*) FROM fato_precos f ANTI JOIN dim_tempo t ON f.data = t.data"),
    ("Chave órfã: fato.cnpj sem dim_posto", "CRITICO",
     "SELECT COUNT(*) FROM fato_precos f ANTI JOIN dim_posto p USING (cnpj)"),
    ("Chave órfã: fato.id_local sem dim_local", "CRITICO",
     "SELECT COUNT(*) FROM fato_precos f ANTI JOIN dim_local l USING (id_local)"),
    ("Chave órfã: fato.id_produto sem dim_produto", "CRITICO",
     "SELECT COUNT(*) FROM fato_precos f ANTI JOIN dim_produto p USING (id_produto)"),
    ("Chave órfã: fato.id_bandeira sem dim_bandeira", "CRITICO",
     "SELECT COUNT(*) FROM fato_precos f ANTI JOIN dim_bandeira b USING (id_bandeira)"),
    ("Produto sem tipo de combustível mapeado", "CRITICO",
     "SELECT COUNT(*) FROM dim_produto WHERE tipo_combustivel IS NULL"),
    ("Região sem nome mapeado", "CRITICO",
     "SELECT COUNT(*) FROM dim_local WHERE regiao_nome IS NULL"),
    (f"Preço fora da faixa plausível ({PRECO_MIN}–{PRECO_MAX})", "ALERTA",
     f"SELECT COUNT(*) FROM fato_precos WHERE valor_venda < {PRECO_MIN} OR valor_venda > {PRECO_MAX}"),
    ("UF associada a mais de uma região", "CRITICO",
     "SELECT COUNT(*) FROM (SELECT uf FROM dim_local GROUP BY uf HAVING COUNT(DISTINCT regiao_sigla) > 1)"),
    # Esperado: 1 (set/2020 — a ANP não publicou coletas nesse mês). Ver docs/exploracao.md
    ("Meses (ano_mes) sem nenhuma coleta", "ALERTA",
     """SELECT COUNT(*) FROM (SELECT DISTINCT ano_mes FROM dim_tempo) m
        WHERE m.ano_mes NOT IN (SELECT DISTINCT strftime(data, '%Y-%m') FROM fato_precos)"""),
]


def fmt(n: int) -> str:
    """Formata número no padrão brasileiro: 5473024 -> 5.473.024"""
    return f"{n:,}".replace(",", ".")


def testes_qualidade(con: duckdb.DuckDBPyConnection) -> bool:
    linhas_md = [
        "# Relatório de qualidade dos dados",
        "",
        f"Gerado por `src/load_data.py` em {time.strftime('%d/%m/%Y %H:%M')}.",
        "",
        "## Volume por tabela",
        "| Tabela | Linhas |",
        "|---|---:|",
    ]
    for tabela in ["stg_bruto", "fato_precos", "dim_tempo", "dim_local", "dim_produto", "dim_bandeira", "dim_posto"]:
        n = con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
        linhas_md.append(f"| {tabela} | {fmt(n)} |")

    linhas_md += ["", "## Testes", "| Teste | Tipo | Resultado | Status |", "|---|---|---:|---|"]
    tudo_ok = True
    for nome, tipo, sql in TESTES:
        qtd = con.execute(sql).fetchone()[0]
        if tipo == "INFO":
            status = "ℹ️"
        elif qtd == 0:
            status = "✅"
        elif tipo == "ALERTA":
            status = "⚠️"
        else:
            status = "❌"
            tudo_ok = False
        log(f"{status} {nome}: {qtd}")
        linhas_md.append(f"| {nome} | {tipo} | {fmt(qtd)} | {status} |")

    RELATORIO.parent.mkdir(parents=True, exist_ok=True)
    RELATORIO.write_text("\n".join(linhas_md) + "\n", encoding="utf-8")
    log(f"relatório salvo em {RELATORIO.relative_to(RAIZ)}")
    return tudo_ok


# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Carga e modelagem da base ANP")
    parser.add_argument("--db", type=Path, default=DB_PADRAO, help="caminho do arquivo DuckDB")
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    if args.db.exists():
        args.db.unlink()  # recria do zero: a carga é idempotente

    inicio = time.time()
    # Todo o trabalho pesado (staging) acontece num banco EM MEMÓRIA.
    # Se fizéssemos no arquivo final e depois apagássemos o staging, o espaço apagado
    # continuaria ocupado no arquivo (o DuckDB não "encolhe" o arquivo): ~535 MB contra ~48 MB.
    con = duckdb.connect()
    # limites para rodar em notebook simples; arquivos temporários fora do projeto
    con.execute("SET memory_limit = '2GB'")
    con.execute(f"SET temp_directory = '{Path(tempfile.gettempdir()).as_posix()}/duckdb_tmp'")

    log("1/6 lendo CSVs brutos");          ler_bruto(con)
    log("2/6 limpando e padronizando");    limpar(con)
    log("3/6 criando dimensões");          criar_dimensoes(con)
    log("4/6 criando fato");               criar_fato(con)
    log("5/6 testes de qualidade");        ok = testes_qualidade(con)

    # Só as tabelas do modelo estrela vão para o arquivo final (o staging não interessa à LLM)
    log("6/6 gravando modelo estrela em disco")
    con.execute(f"ATTACH '{args.db.as_posix()}' AS final")
    for tabela in TABELAS_FINAIS:
        con.execute(f"CREATE TABLE final.{tabela} AS SELECT * FROM {tabela}")
    con.execute("DETACH final")
    con.close()

    log(f"concluído em {time.time() - inicio:.0f}s -> {args.db}")
    if not ok:
        sys.exit("❌ Algum teste CRÍTICO falhou. Veja docs/qualidade_dados.md")


if __name__ == "__main__":
    main()
