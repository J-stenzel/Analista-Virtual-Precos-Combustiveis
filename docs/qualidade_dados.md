# Relatório de qualidade dos dados

Gerado por `src/load_data.py` em 24/11/2026 12:15.

Período da base: 01/01/2020 a 21/11/2026.

## Relatórios semanais (data/raw_semanal)
| Item | Linhas |
|---|---:|
| Arquivos .xlsx | 21 |
| Linhas lidas | 424.948 |
| Descartadas: GLP (fora da série histórica) | 68.162 |
| Descartadas: datas que a série semestral já tem | 11.472 |
| Acrescentadas à base | 345.314 |

## Volume por tabela
| Tabela | Linhas |
|---|---:|
| stg_bruto | 5.818.338 |
| fato_precos | 5.809.204 |
| dim_tempo | 2.517 |
| dim_local | 471 |
| dim_produto | 6 |
| dim_bandeira | 77 |
| dim_posto | 21.184 |

## Testes
| Teste | Tipo | Resultado | Status |
|---|---|---:|---|
| Linhas vazias removidas (informativo) | INFO | 9.114 | ℹ️ |
| Registros de origem agregados por duplicidade (informativo) | INFO | 20 | ℹ️ |
| Postos sem rua no cadastro (informativo; não serão geocodificados pelo endereço) | INFO | 0 | ℹ️ |
| Nulos em colunas-chave da fato | CRITICO | 0 | ✅ |
| Duplicatas no grão (data, cnpj, produto) | CRITICO | 0 | ✅ |
| CNPJ com tamanho diferente de 14 dígitos | CRITICO | 0 | ✅ |
| Chave órfã: fato.data sem dim_tempo | CRITICO | 0 | ✅ |
| Chave órfã: fato.cnpj sem dim_posto | CRITICO | 0 | ✅ |
| Chave órfã: fato.id_local sem dim_local | CRITICO | 0 | ✅ |
| Chave órfã: fato.id_produto sem dim_produto | CRITICO | 0 | ✅ |
| Chave órfã: fato.id_bandeira sem dim_bandeira | CRITICO | 0 | ✅ |
| Produto sem tipo de combustível mapeado | CRITICO | 0 | ✅ |
| Região sem nome mapeado | CRITICO | 0 | ✅ |
| Preço fora da faixa plausível (0.5–20.0) | ALERTA | 0 | ✅ |
| UF ausente ou fora do padrão de 2 letras (ex.: estado do semanal sem sigla mapeada) | CRITICO | 0 | ✅ |
| Produto fora dos 6 da série histórica (ex.: GLP do semanal) | CRITICO | 0 | ✅ |
| UF associada a mais de uma região | CRITICO | 0 | ✅ |
| Meses (ano_mes) sem nenhuma coleta | ALERTA | 1 | ⚠️ |
