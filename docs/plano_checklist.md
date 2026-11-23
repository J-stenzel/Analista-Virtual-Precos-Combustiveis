# Plano do Projeto Final — "Do BI ao Analista Virtual" (base ANP — preços de combustíveis)

Legenda: [ ] a fazer · [x] feito · ❓ = pergunta de entendimento (responda com suas palavras antes de seguir)

## Ideia central (leia antes de tudo)
O sistema NÃO "lê a planilha". Ele recebe uma pergunta, consulta um **dicionário de negócio** (camada semântica), gera **SQL**, executa no banco e explica o resultado. A parte mais importante (e mais avaliada) é a **camada semântica** + a **avaliação com golden set**. Os agentes são a parte "fácil" depois que isso está bem feito.

Tema: **Preços de combustíveis ao consumidor no Brasil** (ANP — Série Histórica de Preços). Foco a confirmar.

---

## Etapa 0 — Preparação
- [x] 0.1 Pasta do projeto criada (`TRABALHO_FINAL_IA`)
- [ ] 0.2 Definir grupo e papéis (dados / camada semântica / agentes / avaliação+README)
- [ ] 0.3 Instalar Python 3.11+, VS Code, Git; criar repositório GitHub
- [ ] 0.4 Escolher LLM (API com tool calling ou local via Ollama) e criar `.env` + `.gitignore`
- ❓ Por que a chave de API fica no `.env` e o `.env` no `.gitignore`?

## Etapa 1 — Problema e dados → Checkpoint 1
- [x] 1.1 Escolher base: ANP — Série Histórica de Preços de Combustíveis
- [x] 1.2 Baixados 13 semestres (2020.01–2026.01) em `data/raw/`
- [x] 1.3 Ler o PDF de metadados (o que significa cada coluna)
- [x] 1.4 Explorar: nº de linhas, colunas, tipos, nulos, separador/encoding, período, produtos (ver `docs/exploracao.md`)
- [x] 1.5 Foco: consulta de preço por atributo (local, produto, bandeira, tempo, posto) + comparações
- [x] 1.6 Desenhar fato + dimensões (rascunho em `docs/exploracao.md`)
- [ ] 1.7 Escrever 10 perguntas de negócio de um gestor (rede de postos, Procon, distribuidora…)
- [ ] 1.8 Montar a página do Checkpoint 1 (tema, fonte, tabelas, 10 perguntas, papéis)
- ❓ Qual a diferença entre tabela fato e dimensão? Dê um exemplo desta base.
- ❓ Por que a coluna "Valor de Compra" não serve para os dados de 2025–2026?

## Etapa 2 — Preparação e modelagem
- [x] 2.1 `load_data.py`: ler CSVs (separador `;`, vírgula decimal, latin-1), limpar tipos e datas
- [x] 2.2 Carregar no DuckDB: `fato_precos`, `dim_posto`, `dim_local`, `dim_produto`, `dim_tempo`
- [x] 2.3 Testes de qualidade: nulos, duplicatas, chaves órfãs, preços zerados/absurdos (`docs/qualidade_dados.md`)
- [ ] 2.4 Escrever `semantic_layer.yaml`: tabelas, colunas, relacionamentos, métricas, sinônimos, regras
- [ ] 2.5 Testar cada métrica do YAML rodando o SQL à mão
- ❓ O que é uma chave órfã e que erro ela causa num JOIN?
- ❓ Por que "preço médio" precisa ser definido no YAML (média simples por coleta? por posto?)

## Etapa 2.5 — Golden set (ANTES dos prompts!)
- [ ] 2.6 Escrever 20 perguntas (7 fáceis, 7 médias, 4 difíceis, 2 armadilhas)
- [ ] 2.7 Escrever o SQL de referência à mão e a resposta esperada → `eval/golden_set.csv`
- ❓ Por que o golden set precisa ser feito antes de ajustar prompts?

## Etapa 3 — Agentes → Checkpoint 2
- [ ] 3.1 `tools.py`: get_schema, get_metric, validate_sql, run_sql (somente leitura, LIMIT, timeout)
- [ ] 3.2 UM agente fazendo tudo de ponta a ponta
- [ ] 3.3 Dividir em 3: Orquestrador, Agente SQL (até 3 tentativas), Analista
- [ ] 3.4 Guardrails: bloquear escrita, recusa fora de escopo, mostrar SQL
- [ ] 3.5 Demo com 3 perguntas
- ❓ O que é tool calling e por que o LLM não executa o SQL "sozinho"?
- ❓ Por que começar com 1 agente só?

## Etapa 4 — Avaliação
- [ ] 4.1 `run_eval.py`: roda as 20 perguntas, compara com a referência
- [ ] 4.2 Medir: acurácia, % SQL válido na 1ª, média de tentativas, tempo médio
- [ ] 4.3 `analise_erros.md`: falha, causa, correção — métricas ANTES e DEPOIS
- ❓ Por que demonstração ao vivo não basta para avaliar um sistema com LLM?

## Etapa 5 — Acabamento
- [ ] 5.1 Interface Streamlit (`app.py`): pergunta → texto + tabela + SQL
- [ ] 5.2 README (como rodar, diagrama, stack e justificativas)
- [ ] 5.3 USO_DE_IA.md
- [ ] 5.4 Ensaiar a apresentação: cada membro explica qualquer parte

---

## Banco de ideias: focos possíveis
| Foco | Métricas | Pergunta de gestor típica |
|---|---|---|
| Variação regional | preço médio por região/UF/município, ranking | "Qual estado tem a gasolina mais cara?" |
| Tendência no tempo | variação % mês a mês, semestre vs semestre | "Quanto a gasolina subiu do 1º sem/2025 para o 1º sem/2026?" |
| Bandeira × bandeira branca | diferença de preço médio, por produto e UF | "Posto de bandeira cobra mais caro?" |
| Etanol compensa? | paridade etanol/gasolina (≤ 70% compensa) | "Em quais estados vale abastecer com etanol?" |
| Concorrência | dispersão (amplitude, desvio padrão) dentro do município | "Onde a diferença entre o posto mais caro e o mais barato é maior?" |
| (Opcional) Demanda | vendas em m³ por UF/mês (outra base da ANP) | "Estados que mais vendem diesel pagam menos?" |

⚠️ É uma pesquisa por amostra de postos (não todos os postos, nem todo dia) → ressalva que o Agente Analista deve citar.
