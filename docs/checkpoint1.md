# Checkpoint 1 — Analista Virtual de Preços de Combustíveis

**Disciplina:** Inteligência Artificial — Projeto Final "Do BI ao Analista Virtual"
**Grupo:** Douglas H. da Silva · Jeferson Stenzel · Leonardo M. L. Rodrigues · Leonardo M. Lima

## Tema
Um analista virtual que responde, em linguagem natural, perguntas sobre **preços de combustíveis ao consumidor no Brasil**.
O usuário consulta preços por local (região, estado, município, CEP), produto, bandeira, período e posto, e faz comparações
(ex.: bandeira × bandeira branca, etanol × gasolina, variação no tempo).

## Fonte dos dados
- **ANP — Série Histórica de Preços de Combustíveis** (Levantamento de Preços de Combustíveis — LPC), dados abertos:
  https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/serie-historica-de-precos-de-combustiveis
- Arquivos semestrais de "Combustíveis automotivos", **jan/2020 a jun/2026** (13 arquivos, ~5,47 milhões de linhas, 16 colunas).
- Sem dados pessoais sensíveis: CNPJ e endereço são de empresas (postos). A coluna "Valor de Compra" foi descartada (só existe até ago/2020).

## Descrição das tabelas (modelo estrela, DuckDB)
| Tabela | Linhas | Grão / conteúdo | Chave |
|---|---:|---|---|
| `fato_precos` | 5.463.890 | 1 preço de venda de 1 produto, em 1 posto, em 1 data de coleta | data + cnpj + id_produto |
| `dim_tempo` | 2.373 | 1 dia: ano, semestre, trimestre, mês, semana, dia da semana | data |
| `dim_local` | 471 | Região → UF → município | id_local |
| `dim_produto` | 6 | gasolina, gasolina aditivada, etanol, diesel, diesel S10, GNV + unidade | id_produto |
| `dim_bandeira` | 76 | bandeira padronizada (ex.: Petrobras Distribuidora/Vibra Energia → VIBRA) + flag bandeira branca | id_bandeira |
| `dim_posto` | 21.103 | CNPJ, razão social, bairro, CEP, 1ª e última coleta | cnpj |

Relacionamentos: `fato_precos` → `dim_tempo` (data), `dim_local` (id_local), `dim_produto` (id_produto), `dim_bandeira` (id_bandeira), `dim_posto` (cnpj).
Qualidade: 15 testes automáticos (nulos, duplicatas, chaves órfãs, faixa de preço) — todos os críticos aprovados. Lacuna conhecida: set/2020 sem coleta.

## As 10 perguntas de negócio
1. Qual é o preço atual da gasolina no CEP 03210-001?
2. Pela regra dos 70%, liste até 10 postos do município de São Paulo onde o etanol compensa na coleta mais recente.
3. Qual município do Brasil tem a maior média de preço atual da gasolina?
4. Qual município do Brasil tem a menor média de preço atual do etanol?
5. Qual é o preço médio do diesel S10 no estado do Paraná no último mês com pesquisa?
6. Quantos postos foram pesquisados em Curitiba no último mês com pesquisa?
7. Como evoluiu, mês a mês, o preço médio da gasolina no Brasil em 2025?
8. Postos bandeira branca são mais baratos que os de bandeira? Diferença média da gasolina por região no último mês com pesquisa.
9. Qual foi a variação % do preço médio da gasolina entre o 1º semestre de 2025 e o 1º semestre de 2026, por estado?
10. Em Belo Horizonte, qual a diferença entre o posto mais caro e o mais barato do etanol no último mês com pesquisa?

**Regras de negócio principais:** "atual" = última coleta do posto ou último mês com pesquisa do local; rankings entre locais usam o
último trimestre com pesquisa e exigem ≥ 5 postos; etanol compensa se custar ≤ 70% da gasolina (mesmo posto e data);
**toda resposta informa a data/período da pesquisa**.

## Papéis no grupo
Por decisão do grupo, **cada integrante desenvolve o projeto completo, do início ao fim** (dados, camada semântica, agentes,
avaliação e interface), com foco no aprendizado de todas as etapas. Assim, todos os membros sabem explicar qualquer parte do projeto.

| Integrante | Papel |
|---|---|
| Douglas H. da Silva | Todas as etapas (projeto individual) |
| Jeferson Stenzel | Todas as etapas (projeto individual) |
| Leonardo M. L. Rodrigues | Todas as etapas (projeto individual) |
| Leonardo M. Lima | Todas as etapas (projeto individual) |
