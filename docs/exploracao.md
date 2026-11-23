# Etapa 1.4 — Resultado da exploração (21/11/2026)

Script: `src/explorar_dados.py` · saída completa: `docs/exploracao_saida.txt`

## Visão geral
- **13 arquivos semestrais**, 2020.01 a 2026.01 (2022.01 baixado depois).
- **5.473.024 linhas** (após incluir 2022.01), 16 colunas (+ "Valor de Compra", descartada).
- **27 UFs, 470 municípios, ~21 mil postos** (CNPJs distintos), 5 regiões.
- Período: 01/01/2020 a 30/06/2026.
- Produtos: GASOLINA, GASOLINA ADITIVADA, ETANOL, DIESEL, DIESEL S10 (R$/litro) e GNV (R$/m³).

## Problemas de qualidade encontrados → tratamento no `load_data.py`
| # | Problema | Onde | Tratamento |
|---|---|---|---|
| 1 | Codificação diferente (latin-1) | 2021.02 | detectar encoding por arquivo |
| 2 | 9.114 linhas totalmente vazias | 2025.01 | descartar linhas sem Produto |
| 3 | CNPJ em 2 formatos (`49.051.667/0001-02` e `03698504000115`) | 2025.02 | manter só dígitos |
| 4 | Unidade do GNV escrita de 2 jeitos (`R$ / m³` e `R$ / m3`) | — | padronizar `R$ / m³` |
| 5 | Mesma distribuidora com nomes diferentes no tempo | todos | mapear para um nome único (ver abaixo) |
| 6 | ~15 linhas duplicadas | — | remover duplicatas |
| 7 | Valor com vírgula decimal, data `dd/mm/aaaa` | todos | converter tipos |
| 8 | Arquivo 2022.01 ausente | — | ✅ baixado |
| 9 | Setembro/2020 sem nenhuma coleta | 2020.02 | lacuna da própria ANP: documentar como ressalva |
| 10 | Bandeiras FEDERAL → FEDERAL ENERGIA e TOTAL BRASIL → TOTALENERGIES | — | incluídas no mapeamento |

### Renomeações de bandeira
| Nome no arquivo | Período | Nome padronizado |
|---|---|---|
| PETROBRAS DISTRIBUIDORA S.A. | 2020-01 → 2021-02 | VIBRA |
| VIBRA ENERGIA | 2021-02 → 2023-07 | VIBRA |
| VIBRA | 2023-07 → hoje | VIBRA |
| ALESAT | 2020-01 → 2024-05 | ALE |
| ALE | 2024-05 → hoje | ALE |

## Modelo dimensional (estrela)
```
                 dim_tempo
                     │
dim_local ── fato_precos ── dim_produto
   │                 │
dim_posto ───────────┘── dim_bandeira
```
- **fato_precos** (grão: 1 coleta = posto × produto × data): data, cnpj, id_local, id_produto, id_bandeira, valor_venda
- **dim_local**: região → UF → município (hierarquia)
- **dim_tempo**: data, dia da semana, semana, mês, trimestre, semestre, ano
- **dim_produto**: produto, tipo (gasolina/etanol/diesel/gnv), unidade
- **dim_bandeira**: bandeira original, bandeira padronizada, é_branca (s/n)
- **dim_posto**: cnpj, razão social, bairro, cep (endereço completo descartado)

Por que a bandeira fica na FATO e não só no posto: um posto pode trocar de bandeira; a bandeira certa é a do dia da coleta.
