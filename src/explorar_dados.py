"""
Etapa 1.4 — Exploração dos dados brutos da ANP (Série Histórica de Preços de Combustíveis).

Objetivo: CONHECER os dados antes de modelar. Nada é gravado no banco aqui.
Como rodar (na pasta do projeto):  python src/explorar_dados.py

Boas práticas aplicadas:
- Ler tudo como texto (all_varchar) primeiro: assim nenhum valor "estranho" quebra a leitura,
  e a conversão de tipos fica explícita e controlada no load_data.py.
- Detectar a codificação por arquivo: a ANP mistura UTF-8 e latin-1 (ISO-8859).
- Ignorar "Valor de Compra" (decisão do projeto: só existe até ago/2020).
"""
from pathlib import Path
import duckdb

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def detectar_encoding(caminho: Path) -> str:
    """Tenta ler o arquivo como UTF-8; se falhar, assume latin-1."""
    with open(caminho, "rb") as f:
        amostra = f.read(5_000_000)
    try:
        amostra.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


con = duckdb.connect()  # banco em memória, só para explorar
partes = []
for arq in sorted(RAW.glob("*.csv")):
    enc = detectar_encoding(arq)
    periodo = arq.stem.split("_")[-1]  # ex.: 2025.01
    partes.append(
        f"""SELECT '{periodo}' AS arquivo, *
            FROM read_csv('{arq.as_posix()}', delim=';', header=true,
                          all_varchar=true, encoding='{enc}')"""
    )
    print(f"{arq.name}: encoding={enc}")

con.execute("CREATE TABLE bruto AS " + " UNION ALL BY NAME ".join(partes))
con.execute('ALTER TABLE bruto DROP COLUMN "Valor de Compra"')


def mostrar(titulo, sql):
    print(f"\n### {titulo}")
    print(con.sql(sql))


mostrar("Linhas por arquivo", "SELECT arquivo, COUNT(*) linhas FROM bruto GROUP BY 1 ORDER BY 1")
mostrar("Total de linhas", "SELECT COUNT(*) FROM bruto")
mostrar("Colunas", "DESCRIBE bruto")
mostrar("Nulos por coluna",
        "SELECT " + ", ".join(
            f'SUM(CASE WHEN "{c}" IS NULL OR TRIM("{c}") = \'\' THEN 1 ELSE 0 END) AS "{c}"'
            for c in [r[0] for r in con.execute("DESCRIBE bruto").fetchall()]
        ) + " FROM bruto")
mostrar("Regiões", 'SELECT "Regiao - Sigla", COUNT(*) n FROM bruto GROUP BY 1 ORDER BY 2 DESC')
mostrar("Qtd de estados, municípios e postos",
        """SELECT COUNT(DISTINCT "Estado - Sigla") estados,
                  COUNT(DISTINCT "Estado - Sigla" || '|' || "Municipio") municipios,
                  COUNT(DISTINCT regexp_replace("CNPJ da Revenda", '[^0-9]', '', 'g')) postos
           FROM bruto""")
mostrar("Produtos e unidades",
        'SELECT "Produto", "Unidade de Medida", COUNT(*) n FROM bruto GROUP BY 1,2 ORDER BY 3 DESC')
mostrar("Bandeiras (top 25)",
        'SELECT "Bandeira", COUNT(*) n FROM bruto GROUP BY 1 ORDER BY 2 DESC LIMIT 25')
mostrar("Período coberto",
        """SELECT MIN(strptime("Data da Coleta", '%d/%m/%Y')) inicio,
                  MAX(strptime("Data da Coleta", '%d/%m/%Y')) fim FROM bruto""")
mostrar("Formatos de CNPJ (amostra)",
        """SELECT length(TRIM("CNPJ da Revenda")) tamanho, COUNT(*) n, ANY_VALUE("CNPJ da Revenda") exemplo
           FROM bruto GROUP BY 1 ORDER BY 2 DESC""")
mostrar("Preço por produto (mín / médio / máx)",
        """SELECT "Produto",
                  MIN(CAST(REPLACE("Valor de Venda", ',', '.') AS DOUBLE)) minimo,
                  ROUND(AVG(CAST(REPLACE("Valor de Venda", ',', '.') AS DOUBLE)), 3) medio,
                  MAX(CAST(REPLACE("Valor de Venda", ',', '.') AS DOUBLE)) maximo
           FROM bruto GROUP BY 1 ORDER BY 1""")
mostrar("Linhas duplicadas exatas",
        "SELECT COUNT(*) - (SELECT COUNT(*) FROM (SELECT DISTINCT * EXCLUDE (arquivo) FROM bruto)) FROM bruto")
