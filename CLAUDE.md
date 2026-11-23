# CLAUDE.md — Projeto Final de IA: "Do BI ao Analista Virtual"

> Lido automaticamente pelo Claude Code ao abrir esta pasta.
> Contém: como o aluno quer trabalhar, resumo do enunciado, decisões tomadas, mapa de arquivos e **onde paramos**.
> Histórico completo de progresso: `STATUS.md`. Enunciado original: `docs/Projeto_Final_Analista_Virtual.pdf`.

## ▶️ ONDE PARAMOS (atualizar ao fim de cada sessão)
- Última sessão: 22/11/2026 (migração do claude.ai para o Claude Code).
- **Etapa atual: 2.5 — `src/semantic_layer.yaml`**, construído em micro-passos:
  - ✅ 2.5.1 seção `projeto` + `tabelas` (6 tabelas, todas as colunas descritas)
  - ✅ 2.5.2 `relacionamentos` (5 JOINs N:1 verificados, `aliases_padrao` f/t/p/l/pr/b, `joins_proibidos`)
  - ✅ 2.5.3 `metricas` (10 métricas + `padrao_media_por_posto`; exemplos testados no banco)
  - ✅ 2.5.4 `sinonimos` (produtos, bandeiras, regiões, 27 UFs, apelidos de municípios, termos ambíguos,
    termos fora da base, palavras → métricas, períodos; 61 valores conferidos no banco, 0 erros)
  - ✅ 2.5.5 `regras_de_negocio` (R01–R14 + `checklist_sql` + `ressalvas`; SQL dos exemplos testado no banco)
  - ✅ 2.5.6 `tests/testar_camada_semantica.py` (89 verificações OK) + notebook atualizado para média por posto e reexecutado
- ✅ 2.7 `docs/Etapa2_Preparacao_e_Modelagem.pdf` (2 páginas; fonte em `docs/etapa2.html`) → **Etapa 2 concluída**.
- ✅ **Golden set** `eval/golden_set.csv` (20 perguntas: 7/7/4/2; 10 do notebook + 10 novas; SQL testado; armadilhas:
  #19 "São Paulo" ambíguo, #20 margem fora da base) + `eval/conferir_golden_set.py` (tudo OK). Fechado ANTES de qualquer prompt.
  ⚠️ NÃO usar as perguntas/respostas do golden set para escrever prompts ou exemplos (overfitting).
- **Etapa 3 — agentes (em andamento).**
  - ✅ 3.0 LLM escolhida: **OpenAI** (orçamento US$ 10, aluno complementa até +US$ 10; prioridade = qualidade).
    Modelos no `.env` (final, após a Etapa 4): Orquestrador `gpt-6.1-terra`, Agente SQL `gpt-6.2-sol`,
    Analista `gpt-6-luna`. SDK `openai` instalado.
  - ✅ 3.0b Chave no `.env` verificada (23/11): aceita, 99 modelos visíveis, os 4 candidatos disponíveis.
  - ✅ 3.1 `src/tools.py` + `tests/testar_tools.py` (54 verificações OK, sem LLM). Segurança em camadas (pedido do aluno,
    "SQL injection"): parser oficial (1 comando SELECT), árvore da consulta (só as 6 tabelas/CTEs, sem funções de tabela,
    getenv, relógio R01), EXPLAIN, conexão read_only + sem acesso externo + lock_configuration, LIMIT 100, timeout 30 s,
    log `logs/sql_bloqueado.log`. R11/R12/R13 = avisos (não bloqueiam). Golden set: 18 SQLs passam sem erro nem aviso.
  - ✅ 3.1b `eval/perguntas_dev.csv` (13 perguntas de DESENVOLVIMENTO: D1–D9 com SQL de referência conferido,
    D10–D11 armadilhas, D12–D13 ataques de prompt injection). Usar ESTAS no dia a dia, nunca o golden set.
  - ✅ 3.1c `src/llm.py`: **Responses API** (teste 23/11: na Chat Completions os gpt-6.x só aceitam ferramentas com
    raciocínio desligado). `chamar_llm(agente, instrucoes, entrada, ferramentas)`; modelo/esforço por agente no `.env`;
    custo por chamada em `logs/uso_llm.csv` (`python src/llm.py` mostra o gasto); cache `LLM_CACHE=1` só no
    desenvolvimento. Ciclo ferramenta→resultado→resposta testado. Gasto até agora: < US$ 0,001.
    Obs.: chamada trivial levou ~22 s (latência a observar — afeta a métrica de tempo médio).
  - ✅ 3.2 `src/agente_unico.py` (1 agente de ponta a ponta, gpt-6.2-sol medium) + `src/avaliacao.py` (compara
    VALORES com o SQL de referência). Rodada nas 13 de dev (23/11): **10/13**, SQL válido na 1ª: 9/9, tempo médio
    ~15 s, ~US$ 0,05/pergunta; armadilhas e ataques 4/4. Erros: D3 (comparador rígido demais: referência tem coluna
    extra), D5 ("mais caro" entre estados virou MAX — sinônimo ambíguo na camada semântica), D8 (agente excluiu o DF
    de "estados"). Cache de prompt pegou pouco (~5 mil de ~30 mil tokens) — investigar depois.
    Gasto total até aqui: ~US$ 0,61.
  - ✅ 3.2b Correções achadas no DEV (23/11): sinônimos — "mais caro/barato" entre locais/bandeiras/regiões = PREÇO
    MÉDIO; "maior/menor preço coletado"/"posto mais caro" = máx/mín (também na R05); "estados" = 27 UFs **com o DF**
    (decisão do aluno); `colunas_chave` no `perguntas_dev.csv` + `avaliacao.comparar(...)`. Reteste D3/D5/D7/D8: 4/4
    → **dev agora 13/13**. Gasto total: ~US$ 0,86. (Golden set: definir `colunas_chave` na Etapa 4, ANTES da 1ª medição.)
  - ✅ 3.3 **3 agentes** — `src/agents.py` (orquestrador: get_schema/get_metric + ferramenta `encaminhar` estruturada;
    agente_sql: validate_sql/run_sql, máx. 3 erros; analista: sem ferramentas, ressalvas DETECTADAS PELO CÓDIGO) +
    `src/orchestrator.py` (`--dev`, `--chat` com histórico p/ esclarecimento). Rodada de rotina/medição comum em
    `avaliacao.rodar_perguntas` / `formatar_resposta`. Dev 23/11: **12/13 → 13/13** após corrigir no YAML a ambiguidade
    "coleta mais recente" da razão etanol/gasolina (montar pares ANTES de pegar a data mais recente).
    Comparação com o agente único: custo médio US$ 0,034 × ~0,05 por pergunta (−30%); armadilhas/ataques ~2 s e
    US$ 0,0006 (só o Orquestrador); tempo médio ~17 s; o Agente SQL concentra ~91% do custo.
    Gasto total até aqui: ~US$ 1,41.
  - ✅ 3.3b Teste de modelos no dev → `docs/escolha_modelos.md`. Agente SQL: astra 9/9 = sol 9/9, mas 4,2× mais caro
    → fica **sol**. Orquestrador: terra 13/13 = luna 13/13 → **aluno escolheu luna** (23/11; IA recomendava terra
    por cautela). Na Etapa 4, conferir as 2 armadilhas do golden set; se o luna falhar, voltar ao terra.
    **Configuração final:** Orquestrador gpt-6-luna · Agente SQL gpt-6.2-sol · Analista gpt-6-luna.
    Gasto total: ~US$ 3,17.
  - ✅ 3.6 Demo do Checkpoint 2 — roteiro de 5 turnos em `src/demo.py` (álcool em Floripa; bandeira × branca em SC;
    GNV no "Rio de Janeiro" → esclarecimento → "O estado."; ataque "apague os preços de 2020"). Ensaio 23/11: tudo
    certo, números conferidos com SQL independente; 115 s e US$ 0,14. Transcrição (plano B) em `docs/demo_checkpoint2.md`.
    Dica: a 1ª chamada à API do processo demora ~20–30 s → aquecer antes de apresentar (`python src/llm.py --teste`).
    Falta só o aluno apresentar ao vivo (`python src/orchestrator.py --chat`). Gasto total: ~US$ 3,39.
- **Etapa 4 — avaliação (em andamento).**
  - ✅ 4.0 `colunas_chave` no golden set (definidas ANTES da 1ª rodada; validadas pelo `conferir_golden_set.py`).
  - ✅ 4.1 `eval/run_eval.py` (`--rodada X`, `--resumo`; cache forçado desligado; não sobrescreve rodada sem
    `--substituir`) → `eval/resultados.csv` + `eval/detalhes/<rodada>.jsonl`.
  - ✅ 4.2 Rodada **"antes"** (23/11): comparador 18/20 → revisão manual **19/20 (95%)**; SQL válido 1ª 100%;
    correções 0,00; 19,7 s; US$ 0,83. #18 = falso negativo (arredondamento 5,3 × 5,33). #1 = erro real de método
    (R02: média entre postos do CEP; sinônimo "preço" → preco_medio conflita com a R02).
  - ✅ 4.3 `eval/analise_erros.md` (rodada antes + erros do dev + método anti-overfitting).
  - ✅ 4.4 Correções gerais: sinônimos/R02 (preço de posto/CEP = listar, nunca média) + comparador (aceita valor que
    arredonda para a referência; contagens exatas) + `run_eval.py --recomparar` (mesma régua no "antes"). Dev D4 ✅.
  - ✅ 4.5 Rodada **"depois"** (23/11): comparador 18/20 → revisão **19/20 (95%)**; SQL 1ª 100%; 21,5 s; US$ 0,86.
    #1 corrigida ✅; #15 falso negativo ("até 10 postos" tem 390 respostas válidas; conferido); **#8 erro real**:
    conflito R04 × R05 ("preço atual" em ranking) — o mesmo texto do Orquestrador já existia no "antes" (variação
    entre execuções). `analise_erros.md` atualizado (antes × depois, variação ±1 pergunta).
  - ✅ 4.6 Precedência R05 > R04 no YAML (ranking sem período = trimestre; "último mês" explícito = mesmo mês para
    todos) + 3 perguntas novas de dev (D14–D16, 4/4 ✅) → rodada **"depois_2"**: **18/20 (90%)**. #8 falhou de novo
    (Orquestrador reescreve "atual" como "último mês comum a todos"); **#16 = BUG**: Agente SQL vê 20 linhas, paginou
    com OFFSET e o código guardou o último resultado (7 de 27 UFs). Gasto total: ~US$ 6,21.
  - ✅ 4.7 Bug de paginação corrigido (agents + aviso OFFSET no validate_sql + teste) + Orquestrador não traduz
    expressões de tempo + D17 no dev (27 linhas) → dev 4/4 → **rodada "final" (ÚLTIMA no golden set, combinado)**:
    **18/20 (90%)**; #8 e #16 corrigidas ✅; novas falhas reais: #14 (LIMIT 1 + Analista disse "não é possível
    determinar") e #19 (armadilha: Orquestrador luna assumiu o município de SP). 4 rodadas: 95/95/90/90%.
    `analise_erros.md` com tabela de estabilidade por pergunta. Gasto total: ~US$ 7,32.
  - ✅ 4.8 Melhorias pós-avaliação (sem nova rodada no golden set, validadas no dev D7/D10/D11/D14 = 4/4):
    Orquestrador **de volta ao gpt-6.1-terra**; Analista recebe o SQL executado; `checklist_sql` com "comparar todas
    as opções citadas" e "sem OFFSET". **Etapa 4 concluída.** Gasto total: ~US$ 7,44.
    **Configuração final:** Orquestrador gpt-6.1-terra · Agente SQL gpt-6.2-sol · Analista gpt-6-luna.
- **Etapa 5 — acabamento (em andamento).**
  - ✅ 5.1 `src/app.py` (Streamlit, `streamlit run src/app.py`): cabeçalho com título do projeto + curso (Tecnólogo em
    Banco de Dados — Faculdade de Tecnologia Impacta), matéria (Artificial Intelligence), professor (Me. Cesar Augusto
    Cardoso Caetano); barra lateral azul com logos (ou selos), desenvolvedores, fonte ANP, exemplos clicáveis, modelos e
    gasto da sessão; faixa + 3 cartões (estilo da referência do aluno, cores vivas); conversa com histórico; progresso
    por agente (callback `ao_etapa` no orchestrator); texto + tabela completa + CSV + gráfico automático (Altair, eixo
    ajustado) + SQL sempre visível + detalhes. Tema em `.streamlit/config.toml`; `.claude/launch.json` p/ preview.
    Testado no navegador embutido (Floripa, PR mês a mês, GNV RJ → "O estado.") ✅.
  - ✅ 5.1b Visual refeito com a identidade do site da Impacta (cores lidas da página: fundo #0D181D/#071C23/#020D13,
    azul #116FFF/#0A88F4, ciano #00D8FF, Montserrat, botões contornados; tema escuro no `config.toml`); logos enviados
    pelo aluno em `assets/` (Impacta + ANP num cartão branco no cabeçalho); **esclarecimento mais claro**: o progresso
    diz "Preciso de uma informação sua para continuar" e aparece um aviso "responda na caixa abaixo" (antes dizia
    "Pronto" e o aluno achou que a resposta tinha falhado). Testado: GNV RJ → "O município." = R$ 4,336/m³ ✅ (conferido).
    Gasto total: ~US$ 7,65.
  - ✅ 5.2 `README.md`: logos, curso/matéria/professor/grupo, print da tela (`docs/imagens/`), o que faz, diagrama
    Mermaid da arquitetura, como rodar (venv, banco, `.env`, app, CLI, testes), dados e modelo, camada semântica,
    guardrails, avaliação (4 rodadas), stack e decisões, estrutura, limitações, uso de IA. Números e arquivos citados
    conferidos (21 arquivos existem; 55 testes nas tools).
  - ✅ 5.3 **GitHub:** https://github.com/J-stenzel/Analista-Virtual-Precos-Combustiveis (branch `main`, 57 arquivos,
    `.env` fora; conferido). Git em `C:\Program Files\Git\cmd\git.exe` (o terminal da IA não tem o `git` no PATH).
    Login do GitHub salvo no Git Credential Manager (feito pelo aluno no navegador). O repositório veio com um README
    automático: foi feito merge mantendo o README do projeto (sem `--force`). Commits com "Co-Authored-By: Claude".
  - ⬜ **PRÓXIMO PASSO: Etapa 6 — roteiro da apresentação** (demo ao vivo com perguntas de reserva; todos sabem
    explicar). Commitar e enviar as próximas mudanças ao fim de cada etapa.
  Pendentes menores: fixar versão do DuckDB no requirements; demo do Checkpoint 2 ao vivo (aluno).
  - Na construção dos agentes: separar instrução × dado nos prompts (pergunta só na mensagem do usuário; resultado do
    banco marcado como dados); pedidos de alterar dados/revelar segredos = fora de escopo.
  - Técnicas de custo combinadas: só o pedaço necessário do YAML, cache de prompt (prefixo fixo), Analista recebe
    ~20 linhas, testes sem LLM, cache em disco no desenvolvimento, ~10 perguntas de desenvolvimento, tokens registrados.
- Pendente: fixar a versão do DuckDB no `requirements.txt` (venv tem duckdb 2.0.1; requirements diz `>=1.1`).

## Modo de trabalho (IMPORTANTE)
Grupo: Douglas H. da Silva, Jeferson Stenzel, Leonardo M. L. Rodrigues, Leonardo M. Lima — cada um faz o projeto
completo (decisão do grupo); **esta pasta é a versão do Jeferson**. Todas as entregas citam os 4 nomes.
O aluno quer **fazer e aprender**, não só receber pronto:
- Trabalhar em **micro-etapas** (checklist + subtarefas). Mostrar cada parte e esperar OK antes de seguir.
- Antes de gerar cada arquivo: explicar **o que**, **por quê** e a **boa prática** envolvida.
- Depois de cada etapa: **1–3 perguntas de entendimento** (❓).
- Código simples, comentado em português. Respostas em português.
- Ao concluir algo: atualizar `STATUS.md`, a seção "ONDE PARAMOS" deste arquivo e `USO_DE_IA.md`.
- Nunca colocar chave de API no código; usar `.env` (já no `.gitignore`).

## Ambiente
- Windows, pasta `C:\Users\Jefer\Desktop\TRABALHO_FINAL_IA`, venv em `.venv` (ativar: `.\.venv\Scripts\Activate.ps1`).
- `pip install -r requirements.txt` · recriar o banco: `python src/load_data.py` (~30 s).
- O banco `data/processed/combustiveis.duckdb` (~40 MB) é gerado pela versão do DuckDB instalada no venv;
  arquivos DuckDB de versão mais nova não abrem em versão mais antiga → manter a mesma versão no grupo (fixar no requirements).

## Enunciado (resumo)
Sistema multiagente ("analista virtual") que responde perguntas de negócio em linguagem natural via SQL.
Fluxo: Pergunta → entendimento/contexto → gerar e validar SQL → executar → resposta (texto + tabela + SQL usado).
- **3 agentes obrigatórios:** Orquestrador (`get_schema()`, `get_metric()`; classifica dados/fora de escopo/ambígua),
  Agente SQL (`validate_sql()`, `run_sql()` somente leitura; até 3 tentativas), Agente Analista (opcional `make_chart()`).
- **Camada semântica obrigatória e central:** `src/semantic_layer.yaml`.
- **Guardrails:** bloquear INSERT/UPDATE/DELETE/DROP/ALTER; LIMIT padrão + timeout; recusar fora de escopo com educação;
  sempre mostrar o SQL; chave em `.env`.
- **Golden set:** 20 perguntas (7 fáceis, 7 médias, 4 difíceis, 2 armadilhas) com SQL de referência À MÃO, ANTES de ajustar prompts.
  Métricas: acurácia, % SQL válido na 1ª tentativa, média de tentativas, tempo médio. Antes e depois das correções.
- **Erros a evitar:** CSV no prompt; pandas agent sem camada semântica; ajustar prompt olhando o golden set;
  começar com 3 agentes de uma vez; API key no GitHub.
- Cronograma: 1 Problema e dados (Checkpoint 1) → 2 Preparação/modelagem → 3 Agentes (Checkpoint 2, demo ≥ 3 perguntas)
  → 4 Avaliação → 5 Acabamento (Streamlit + README) → 6 Apresentação.

## Decisões tomadas
- **Base:** ANP — Série Histórica de Preços de Combustíveis, semestres 2020.01 a 2026.01 (13 CSVs em `data/raw/`, ~5,47 mi linhas).
  LaDe e Ola foram consideradas e descartadas.
- "Valor de Compra" **descartada** (só existia até ago/2020). Endereço detalhado descartado (fica bairro e CEP).
- **Banco:** DuckDB (colunar, rápido para agregações, um arquivo só). Staging feito em memória (arquivo final ~40 MB).
- **Bandeiras padronizadas:** PETROBRAS DISTRIBUIDORA S.A./VIBRA ENERGIA → VIBRA; ALESAT → ALE; FEDERAL → FEDERAL ENERGIA;
  TOTAL BRASIL → TOTALENERGIES. Bandeira e local ficam na FATO (podem mudar ao longo do tempo para o mesmo posto).
- Duplicatas no grão (20 casos) → média. Linhas vazias (9.114, arquivo 2025.01) removidas.
- **Set/2020 sem coleta** na ANP (hipótese do aluno: pandemia — a confirmar). Citar como ressalva.
- **Preços fora do padrão NÃO são marcados nem removidos** — o usuário avalia (decisão do aluno).
- **Preço médio = MÉDIA POR POSTO** (decisão do aluno, 22/11): média de cada posto no recorte, depois média dessas médias.
  Mín/máx/amplitude usam as coletas. O notebook `perguntas_negocio.ipynb` já segue essa regra (atualizado em 22/11).
- **"Estados" = as 27 UFs, incluindo o DF** (decisão do aluno, 23/11). "Mais caro/barato" entre grupos = preço médio.
- **Sinônimos (22/11):** "Shell"/"Raízen" = só RAIZEN (RAIZEN MIME é outra bandeira); "Rio" sozinho = município RJ;
  "diesel" sem detalhe = DIESEL comum (S500). Armadilhas da base: bandeira PETROBRASIL ≠ Petrobras, bandeiras "SP" e
  "RIO BRANCO", município "POA" (Poá/SP), "SE" = Sudeste ou Sergipe.

## Regras de negócio (decididas pelo aluno — vão para `regras_de_negocio` no YAML)
- **Preço atual de posto/CEP** = última coleta daquele posto. CEP aceito com ou sem hífen (comparar só dígitos).
- **"Último mês"** = último mês COM PESQUISA no recorte filtrado (ex.: último mês com coleta em Curitiba).
- **Rankings entre locais** = último TRIMESTRE com pesquisa na base (o mesmo período para todos) e mínimo de **5 postos**.
  Se o usuário informar o período, vale o dele (mínimo de 5 postos em CADA período) — ajuste da R05 em 22/11.
- **"Coleta recente"** = descobrir o último mês com dados na base e considerar os **últimos 3 meses** até ele.
- **Etanol compensa** se etanol ÷ gasolina ≤ 0,70, no mesmo posto e na mesma data de coleta.
- **SEMPRE informar a data/período da pesquisa** em respostas sobre "atual"/"último mês"/"recente".
- "Gasolina" = GASOLINA comum (aditivada só se pedirem). Nunca misturar R$/litro com GNV (R$/m³).
- Filtrar município sempre com UF (nomes se repetem entre estados). Municípios estão em MAIÚSCULAS e sem acento.
- (22/11, novas) **Datas relativas pela última data da BASE, nunca CURRENT_DATE** (base termina 30/06/2026);
  "ano passado" = 2025, "este ano" = 2026 incompleto. Preço atual do posto = última coleta **daquele produto**; CEP com
  vários postos → listar todos. **Coleta antiga** = data anterior à janela de coleta recente → avisar.
  GNV à parte em rankings entre produtos. Recorte com < 5 postos (fora de ranking) → avisar, não recusar.
- Todas as regras estão no YAML como R01–R14 (citar o id na análise de erros).

## Modelo de dados implementado (estrela)
- `fato_precos` (5.463.890) — grão: data + cnpj + id_produto; colunas: data, cnpj, id_local, id_produto, id_bandeira, valor_venda,
  qtd_registros_origem, arquivo_origem
- `dim_tempo` (data, ano, semestre, trimestre, mes, ano_mes 'AAAA-MM', semana_iso, dia_semana_num, dia_semana)
- `dim_local` (id_local, regiao_sigla, regiao_nome, uf, municipio)
- `dim_produto` (id_produto, produto, tipo_combustivel, unidade) — 6 produtos
- `dim_bandeira` (id_bandeira, bandeira, eh_bandeira_branca, nomes_originais)
- `dim_posto` (cnpj, razao_social, bairro, cep '00000-000', primeira_coleta, ultima_coleta)

## Mapa de arquivos
| Arquivo | O que é |
|---|---|
| `STATUS.md` | checklist de progresso de todas as etapas (fonte da verdade do andamento) |
| `src/explorar_dados.py` | exploração inicial dos CSVs |
| `src/load_data.py` | carga, limpeza, modelo estrela e 15 testes de qualidade |
| `src/semantic_layer.yaml` | camada semântica completa (6 seções; regras R01–R14) |
| `tests/testar_camada_semantica.py` | testes do YAML contra o banco — rodar sempre que mexer no YAML |
| `src/verificar_openai.py` | confere a chave da OpenAI e os modelos dos agentes, sem gastar créditos |
| `src/tools.py` | get_schema, get_metric, validate_sql, run_sql (guardrails e segurança em camadas) |
| `tests/testar_tools.py` | testes das tools sem LLM: ataques bloqueados, sem falso alarme, LIMIT, timeout, auditoria |
| `logs/sql_bloqueado.log` | auditoria dos SQLs bloqueados (pasta `logs/` fora do Git) |
| `src/llm.py` | único ponto de chamada à OpenAI (Responses API), custo em `logs/uso_llm.csv`, cache de dev |
| `eval/perguntas_dev.csv` | 13 perguntas de desenvolvimento (≠ golden set) com SQL de referência |
| `src/agente_unico.py` | agente único de ponta a ponta (`--dev` roda as perguntas de dev e compara) — base do Agente SQL |
| `src/avaliacao.py` | compara com a referência (valores, `colunas_chave`), formata a resposta e roda conjuntos de perguntas |
| `src/agents.py` | os 3 agentes: orquestrador, agente_sql, analista (+ detecção de ressalvas pelo código) |
| `src/orchestrator.py` | fluxo entre os 3 agentes; CLI: pergunta, `--chat`, `--dev` |
| `docs/escolha_modelos.md` | medição sol × astra (SQL) e terra × luna (Orquestrador) — justificativa para o README |
| `src/demo.py` / `docs/demo_checkpoint2.md` | roteiro da demo do Checkpoint 2 e transcrição do ensaio (plano B) |
| `src/app.py` + `.streamlit/config.toml` + `assets/` | interface Streamlit (`streamlit run src/app.py`), tema e logos |
| `.env.example` → `.env` | chave `OPENAI_API_KEY` + modelo de cada agente (o `.env` nunca vai para o GitHub; não ler/expor) |
| `notebooks/perguntas_negocio.ipynb` | SQL de referência das 10 perguntas (base do golden set; segue R01–R14) |
| `eval/golden_set.csv` | golden set: id, nivel, pergunta, sql_referencia, resposta_esperada, regras_testadas |
| `eval/conferir_golden_set.py` | confere o golden set (estrutura, SQL somente leitura e rodando, sem vazamento no YAML) |
| `eval/run_eval.py` | avaliação oficial: `--rodada antes/depois`, `--resumo` → `eval/resultados.csv`, `eval/detalhes/` |
| `eval/analise_erros.md` | falhas, causas e correções (antes/depois) — entregável do enunciado |
| `docs/perguntas_negocio.md` | as 10 perguntas + regras de negócio |
| `docs/exploracao.md`, `docs/qualidade_dados.md` | achados da exploração e relatório de qualidade |
| `docs/checkpoint1.md` / `docs/Checkpoint1_Problema_e_Dados.pdf` | entrega da Etapa 1 |
| `docs/etapa2.html` / `docs/Etapa2_Preparacao_e_Modelagem.pdf` | entrega da Etapa 2 (editar o HTML e gerar o PDF de novo) |
| `docs/templates/entrega_template.html` + `gerar_pdf.py` | modelo do layout dos PDFs de entrega |
| `USO_DE_IA.md` | registro do uso de IA (exigido) |

## PDFs de entrega
Layout igual ao enunciado: fonte DejaVu Sans, títulos azul `#1F4E79`, tabelas com cabeçalho azul e linhas alternadas `#EEF3FA`,
caixa de destaque com borda azul à esquerda, rodapé "Projeto Final — Do BI ao Analista Virtual · <entrega>" + "Página N".
Gerado a partir de um HTML baseado em `docs/templates/entrega_template.html`
(`python docs/templates/gerar_pdf.py <entrada.html> <saida.pdf>`). Sempre listar os 4 integrantes.
O script usa WeasyPrint se existir; senão (Windows) usa o **Edge headless** com a fonte DejaVu embutida a partir do
`matplotlib` (no requirements). Conferir o PDF gerado e evitar página com 1 bloco só (enxugar texto).
