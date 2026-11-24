"""
Etapa 2 — Carga, limpeza, modelagem (estrela) e testes de qualidade.

Entrada : data/raw/*.csv  (ANP — Série Histórica de Preços de Combustíveis, semestral: jan/2020 a jun/2026)
          data/raw_semanal/*.xlsx  (ANP — Levantamento de Preços, relatórios SEMANAIS por posto, depois de jun/2026)
Saída   : data/processed/combustiveis.duckdb  com o modelo estrela:

                 dim_tempo
                     │
    dim_local ── fato_precos ── dim_produto
                     │
       dim_posto ────┴──── dim_bandeira

Como rodar (na pasta do projeto):
    python src/load_data.py
    python src/load_data.py --db caminho/outro.duckdb   (opcional)
    python src/load_data.py --sem-semanal   (recria a base SÓ com os CSVs semestrais, até 30/06/2026 —
                                             a base em que o golden set foi avaliado)

Etapas do script (cada uma é uma função):
    1. ler_bruto()        -> stg_bruto       (tudo como texto, 1 linha por linha do CSV)
       ler_semanal()      -> + stg_bruto     (converte os .xlsx semanais para as MESMAS colunas do CSV)
    2. limpar()           -> stg_limpo       (tipos, padronizações, linhas vazias, duplicatas)
    3. criar_dimensoes()  -> dim_*           (chaves substitutas inteiras)
    4. criar_fato()       -> fato_precos
    5. testes_qualidade() -> relatório + falha se algum teste CRÍTICO quebrar
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
import time
from pathlib import Path

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
RAW = RAIZ / "data" / "raw"
RAW_SEMANAL = RAIZ / "data" / "raw_semanal"
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

# --- Relatórios SEMANAIS (.xlsx): diferenças em relação aos CSVs semestrais ---
# O estado vem por extenso e não há coluna de região: sigla e região saem destas tabelas.
ESTADO_SIGLA = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM", "BAHIA": "BA", "CEARA": "CE",
    "DISTRITO FEDERAL": "DF", "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA", "MATO GROSSO": "MT",
    "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG", "PARA": "PA", "PARAIBA": "PB", "PARANA": "PR",
    "PERNAMBUCO": "PE", "PIAUI": "PI", "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN",
    "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO", "RORAIMA": "RR", "SANTA CATARINA": "SC", "SAO PAULO": "SP",
    "SERGIPE": "SE", "TOCANTINS": "TO",
}
UF_REGIAO = {
    **dict.fromkeys(["AC", "AM", "AP", "PA", "RO", "RR", "TO"], "N"),
    **dict.fromkeys(["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"], "NE"),
    **dict.fromkeys(["DF", "GO", "MS", "MT"], "CO"),
    **dict.fromkeys(["ES", "MG", "RJ", "SP"], "SE"),
    **dict.fromkeys(["PR", "RS", "SC"], "S"),
}
# Nomes de produto do semanal -> nomes da série histórica (os outros 4 já são iguais)
PRODUTO_SEMANAL = {"GASOLINA COMUM": "GASOLINA", "DIESEL S500": "DIESEL"}
PRODUTOS_FORA_DA_BASE = {"GLP"}   # botijão (R$/13 kg): a série histórica não tem GLP
LINHA_CABECALHO_SEMANAL = 10      # linhas 1–9 = título do relatório; dados a partir da linha 11

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


def ler_semanal(con: duckdb.DuckDBPyConnection) -> dict:
    """Lê os relatórios SEMANAIS (.xlsx) e acrescenta à stg_bruto com as MESMAS colunas (texto) do CSV.
    Assim limpar(), dimensões, fato e testes valem igual para as duas fontes.
    Devolve contagens para o relatório de qualidade."""
    arquivos = sorted(RAW_SEMANAL.glob("*.xlsx"))
    contagem = {"arquivos": len(arquivos), "lidas": 0, "glp": 0, "sobrepostas": 0, "inseridas": 0}
    if not arquivos:
        log("nenhum .xlsx semanal encontrado — base só com os CSVs semestrais")
        return contagem
    # Última data da série semestral: o semanal só acrescenta o que vem DEPOIS (o 1º arquivo repete 29–30/06)
    ultima = con.execute("""SELECT MAX(strptime(TRIM("Data da Coleta"), '%d/%m/%Y'))::DATE FROM stg_bruto
                            WHERE "Produto" IS NOT NULL AND TRIM("Produto") <> ''""").fetchall()[0][0]
    partes = []
    for arq in arquivos:
        # Tudo como texto (dtype=str), como nos CSVs. Os nomes dos arquivos variam (2026-06-28 ou 2026_10_11):
        inicio = "-".join(re.search(r"(\d{4})[-_](\d{2})[-_](\d{2})", arq.stem).groups())
        log(f"lendo {arq.name}")
        df = pd.read_excel(arq, header=LINHA_CABECALHO_SEMANAL - 1, dtype=str)
        df.columns = [str(c).strip().upper() for c in df.columns]
        df["arquivo_origem"] = f"semanal {inicio}"
        partes.append(df)
    s = pd.concat(partes, ignore_index=True)
    contagem["lidas"] = len(s)

    # Filtros: produto fora da base (GLP) e datas que a série semestral já tem
    produto = s["PRODUTO"].str.strip().str.upper()
    data = pd.to_datetime(s["DATA DA COLETA"].str.strip()).dt.date
    contagem["glp"] = int(produto.isin(PRODUTOS_FORA_DA_BASE).sum())
    contagem["sobrepostas"] = int((~produto.isin(PRODUTOS_FORA_DA_BASE) & (data <= ultima)).sum())
    manter = ~produto.isin(PRODUTOS_FORA_DA_BASE) & (data > ultima)
    s, produto, data = s[manter], produto[manter], data[manter]

    # Conversão para o formato do CSV (colunas extras — FANTASIA, ENDEREÇO, NÚMERO, COMPLEMENTO — ficam de fora)
    uf = s["ESTADO"].str.strip().str.upper().map(ESTADO_SIGLA)          # sem mapa -> nulo -> teste CRÍTICO
    cnpj = s["CNPJ"].str.replace(r"\D", "", regex=True).str.zfill(14)    # Excel guardou como número: perdeu zeros
    cep = s["CEP"].fillna("").str.replace(r"\D", "", regex=True).str.zfill(8)
    convertido = pd.DataFrame({
        "arquivo_origem": s["arquivo_origem"],
        "Regiao - Sigla": uf.map(UF_REGIAO),
        "Estado - Sigla": uf,
        "Municipio": s["MUNICÍPIO"],
        "Revenda": s["RAZÃO"],
        "CNPJ da Revenda": cnpj,
        "Bairro": s["BAIRRO"],
        # mesmo formato da base (00000-000); CEP vazio ou "0" fica nulo (não inventa um CEP 00000-000)
        "Cep": (cep.str[:5] + "-" + cep.str[5:]).where(cep.str.strip("0") != "", None),
        "Produto": produto.replace(PRODUTO_SEMANAL),
        "Data da Coleta": pd.to_datetime(data).dt.strftime("%d/%m/%Y"),
        "Valor de Venda": s["PREÇO DE REVENDA"].astype(float).round(3).map("{:.3f}".format),
        "Unidade de Medida": s["UNIDADE DE MEDIDA"],
        "Bandeira": s["BANDEIRA"],
    })
    con.register("semanal_convertido", convertido)
    con.execute("INSERT INTO stg_bruto BY NAME SELECT * FROM semanal_convertido")   # colunas ausentes = NULL
    con.unregister("semanal_convertido")
    contagem["inseridas"] = len(convertido)
    log(f"semanal: {fmt(contagem['lidas'])} lidas, {fmt(contagem['glp'])} de GLP descartadas, "
        f"{fmt(contagem['sobrepostas'])} já existentes (até {ultima:%d/%m/%Y}) descartadas, "
        f"{fmt(contagem['inseridas'])} acrescentadas")
    return contagem


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
    ("UF ausente ou fora do padrão de 2 letras (ex.: estado do semanal sem sigla mapeada)", "CRITICO",
     "SELECT COUNT(*) FROM dim_local WHERE uf IS NULL OR length(uf) <> 2"),
    ("Produto fora dos 6 da série histórica (ex.: GLP do semanal)", "CRITICO",
     "SELECT COUNT(*) FROM dim_produto WHERE produto NOT IN "
     "('GASOLINA', 'GASOLINA ADITIVADA', 'ETANOL', 'DIESEL', 'DIESEL S10', 'GNV')"),
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


def testes_qualidade(con: duckdb.DuckDBPyConnection, semanal: dict | None = None) -> bool:
    linhas_md = [
        "# Relatório de qualidade dos dados",
        "",
        f"Gerado por `src/load_data.py` em {time.strftime('%d/%m/%Y %H:%M')}.",
        "",
    ]
    periodo = con.execute("SELECT MIN(data), MAX(data) FROM fato_precos").fetchall()[0]
    linhas_md += [f"Período da base: {periodo[0]:%d/%m/%Y} a {periodo[1]:%d/%m/%Y}.", ""]
    if semanal:
        linhas_md += [
            "## Relatórios semanais (data/raw_semanal)",
            "| Item | Linhas |", "|---|---:|",
            f"| Arquivos .xlsx | {semanal['arquivos']} |",
            f"| Linhas lidas | {fmt(semanal['lidas'])} |",
            f"| Descartadas: GLP (fora da série histórica) | {fmt(semanal['glp'])} |",
            f"| Descartadas: datas que a série semestral já tem | {fmt(semanal['sobrepostas'])} |",
            f"| Acrescentadas à base | {fmt(semanal['inseridas'])} |",
            "",
        ]
    linhas_md += [
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
    parser.add_argument("--sem-semanal", action="store_true",
                        help="ignora data/raw_semanal (recria a base até 30/06/2026, a do golden set)")
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

    log("1/7 lendo CSVs brutos");          ler_bruto(con)
    semanal = None
    if args.sem_semanal:
        log("2/7 relatórios semanais IGNORADOS (--sem-semanal)")
    else:
        log("2/7 lendo relatórios semanais");  semanal = ler_semanal(con)
    log("3/7 limpando e padronizando");    limpar(con)
    log("4/7 criando dimensões");          criar_dimensoes(con)
    log("5/7 criando fato");               criar_fato(con)
    log("6/7 testes de qualidade");        ok = testes_qualidade(con, semanal)

    # Só as tabelas do modelo estrela vão para o arquivo final (o staging não interessa à LLM)
    log("7/7 gravando modelo estrela em disco")
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
