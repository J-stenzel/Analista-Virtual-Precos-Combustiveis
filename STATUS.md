# STATUS DO PROJETO — "Do BI ao Analista Virtual" (base ANP)

> Checklist de acompanhamento baseado no cronograma (seção 4) e nos entregáveis (seção 5) do enunciado.
> Legenda: ✅ feito · 🔄 em andamento · ⬜ a fazer
> Última atualização: 23/11/2026

## Resumo
| Etapa | Entrega | Status |
|---|---|---|
| 0. Preparação do ambiente | pasta, venv, dependências | ✅ |
| 1. Problema e dados | Checkpoint 1 (1 página) | ✅ |
| 2. Preparação e modelagem | `load_data.py` + `semantic_layer.yaml` (+ PDF da Etapa 2) | ✅ |
| 2.5 Golden set | `eval/golden_set.csv` (20 perguntas) | ✅ |
| 3. Agentes | Checkpoint 2 (demo com ≥ 3 perguntas) — falta apresentar ao vivo | 🔄 |
| 4. Avaliação | `resultados.csv` + `analise_erros.md` (4 rodadas: 95/95/90/90%) | ✅ |
| 5. Acabamento | interface Streamlit ✅ + README ✅ + GitHub ✅ | ✅ |
| 6. Apresentação | apresentação do grupo | ⬜ |

---

## 0. Preparação do ambiente ✅
- ✅ Pasta do projeto criada (`TRABALHO_FINAL_IA`)
- ✅ `CLAUDE.md` com contexto e decisões (para usar no Claude Code)
- ✅ Ambiente virtual `.venv` criado e funcionando
- ✅ `requirements.txt`
- ✅ `.gitignore` (`.env`, dados grandes, `.venv`)
- ✅ `.env.example`
- ✅ Repositório no GitHub (privado) e 1º commit: https://github.com/J-stenzel/Analista-Virtual-Precos-Combustiveis
- ✅ Definir LLM: **OpenAI**, modelos mesclados por agente (Orquestrador gpt-6-luna · SQL gpt-6.2-sol · Analista gpt-6-luna — ver `docs/escolha_modelos.md`)
- ✅ `.env` com a chave da OpenAI, conferido com `python src/verificar_openai.py` (23/11: chave aceita, modelos disponíveis)

## 1. Problema e dados → Checkpoint 1 ✅
- ✅ 1.1 Tema e base escolhidos: ANP — Série Histórica de Preços de Combustíveis
- ✅ 1.2 Dados baixados: 13 semestres (2020.01 a 2026.01) em `data/raw/`
- ✅ 1.3 PDF de metadados da ANP salvo em `docs/`
- ✅ 1.4 Exploração dos dados (`src/explorar_dados.py`, `docs/exploracao.md`)
- ✅ 1.5 Foco: usuário consulta preço por atributo (local, produto, bandeira, tempo, posto) + comparações
- ✅ 1.6 Desenhar modelo fato + dimensões
- ✅ 1.7 10 perguntas de negócio + regras de negócio (`docs/perguntas_negocio.md`) — revisar com o grupo
- ✅ 1.8 Papéis: cada integrante faz o projeto completo (decisão do grupo)
- ✅ 1.9 Página do Checkpoint 1 (`docs/checkpoint1.md` + `docs/Checkpoint1_Problema_e_Dados.pdf`) — falta entregar
- ✅ 1.10 Notebook com o SQL de referência das 10 perguntas (`notebooks/perguntas_negocio.ipynb`)

## 2. Preparação e modelagem ✅
- ✅ 2.1 `src/load_data.py`: leitura, limpeza e padronização
  - ✅ Encoding por arquivo (UTF-8 / latin-1)
  - ✅ Remoção de linhas vazias (9.114)
  - ✅ CNPJ só com dígitos; unidade do GNV padronizada
  - ✅ Bandeiras renomeadas unificadas (Vibra, Ale, Federal Energia, TotalEnergies)
  - ✅ "Valor de Compra" descartada
  - ✅ Duplicatas no grão tratadas (20)
- ✅ 2.2 Banco DuckDB em `data/processed/combustiveis.duckdb`
  - ✅ `fato_precos` (5,46 mi linhas)
  - ✅ `dim_tempo`, `dim_local`, `dim_produto`, `dim_bandeira`, `dim_posto`
  - ✅ Arquivo otimizado: 535 MB → ~40 MB (staging em memória)
- ✅ 2.3 Testes de qualidade: nulos, duplicatas, chaves órfãs, faixa de preço (`docs/qualidade_dados.md`)
  - ✅ Lacuna documentada: set/2020 sem coleta (hipótese: pandemia — confirmar)
- ✅ 2.4 Testar `load_data.py` no computador do aluno (dentro do venv)
- ✅ 2.5 `src/semantic_layer.yaml` (6 seções completas)
  - ✅ Tabelas e descrição de cada coluna (+ seção "projeto": o que a base tem e não tem)
  - ✅ Relacionamentos (joins) — 5 JOINs N:1 verificados no banco (0 órfãos; os 5 juntos mantêm 5.463.890 linhas) + aliases padrão + joins proibidos
  - ✅ Métricas — 10 métricas; preço médio = **média por posto** (decisão do aluno); exemplos testados no banco
  - ✅ Sinônimos — produtos, bandeiras, regiões, 27 UFs, apelidos de municípios, termos ambíguos e fora da base,
    palavras → métricas, períodos; 61 valores-alvo conferidos no banco (0 erros)
  - ✅ Regras de negócio — R01–R14 + checklist do Agente SQL + ressalvas do Agente Analista; exemplos testados no banco
- ✅ 2.6 Testar cada métrica do YAML
  - ✅ `tests/testar_camada_semantica.py`: estrutura do YAML, todo SQL completo roda, sinônimos existem no banco,
    métricas conferidas em pandas a partir das linhas brutas — 89 verificações OK
  - ✅ `notebooks/perguntas_negocio.ipynb` atualizado: média por posto (P3, P4, P5, P7, P8, P9), `coleta_antiga` na P1,
    apelidos padrão, regras R01–R14 citadas; reexecutado sem erros (P9: AP passou de 5º para 3º)
- ✅ 2.7 `docs/Etapa2_Preparacao_e_Modelagem.pdf` (2 páginas, layout do Checkpoint 1; fonte `docs/etapa2.html`)
  - ✅ `gerar_pdf.py` passou a funcionar no Windows (Edge headless + DejaVu do matplotlib)

## 2.5 Golden set (ANTES de ajustar os prompts!) ✅
- ✅ 20 perguntas: 7 fáceis · 7 médias · 4 difíceis · 2 armadilhas (10 do notebook + 10 novas, nenhuma igual a exemplo do YAML)
- ✅ SQL de referência para cada uma (somente leitura, sem CURRENT_DATE, seguindo R01–R14), todos rodando no banco
- ✅ Resposta esperada de cada uma (com números, período e avisos; armadilhas: pedir esclarecimento / recusar)
- ✅ `eval/golden_set.csv` (id, nivel, pergunta, sql_referencia, resposta_esperada, regras_testadas)
- ✅ `eval/conferir_golden_set.py` — estrutura, distribuição, SQL somente leitura, sem vazamento no YAML: tudo OK
- ✅ R05 ajustada: com período informado pelo usuário, vale o período dele (mín. 5 postos em cada período)

## 3. Agentes → Checkpoint 2 🔄
- ✅ 3.0 LLM: OpenAI, modelos mesclados por agente; chave no `.env` verificada (`src/verificar_openai.py`)
- ✅ 3.1 `src/tools.py` + `tests/testar_tools.py` (54 verificações OK, sem LLM e sem custo)
  - ✅ `get_schema()` (tabelas pedidas + relacionamentos + apelidos + joins proibidos)
  - ✅ `get_metric()` (catálogo ou definição completa + padrão da média por posto)
  - ✅ `validate_sql()` (parser: 1 comando SELECT; árvore: só as 6 tabelas, sem funções de arquivo/sistema/relógio; EXPLAIN; avisos R11/R12/R13)
  - ✅ `run_sql()` (valida de novo; conexão read_only + sem acesso externo + config travada; LIMIT 100; timeout 30 s; log de bloqueios)
  - ✅ 25 ataques/consultas proibidas bloqueados; consultas legítimas sem falso alarme; 18 SQLs do golden set sem erro
- ✅ 3.1b `eval/perguntas_dev.csv` — 13 perguntas de desenvolvimento (9 com SQL conferido, 2 armadilhas, 2 ataques)
- ✅ 3.1c `src/llm.py` — Responses API (ferramentas + raciocínio), modelo/esforço por agente, custo em `logs/uso_llm.csv`, cache de desenvolvimento; testado (gasto < US$ 0,001)
- ✅ 3.2 UM agente funcionando de ponta a ponta (`src/agente_unico.py`) — perguntas de dev: 10/13, SQL válido na 1ª 9/9,
  armadilhas/ataques 4/4, ~15 s e ~US$ 0,05 por pergunta
  - ✅ Correções da camada semântica achadas no dev (sinônimo "mais caro" = média entre grupos; "estados" inclui o DF) + `colunas_chave` no comparador → reteste 4/4, dev **13/13**
- ✅ 3.3 3 agentes (`src/agents.py`) + fluxo (`src/orchestrator.py`, com `--chat` e `--dev`) — dev **13/13**,
  SQL válido na 1ª 9/9, ~17 s e ~US$ 0,034 por pergunta (−30% vs agente único); D9 corrigido no YAML
- ✅ 3.3b Teste de modelos no dev (`docs/escolha_modelos.md`): SQL sol = astra em acerto (9/9), astra 4,2× mais caro → sol;
  Orquestrador terra = luna (13/13) → **aluno escolheu luna**. Configuração final: luna / sol / luna
- 🔄 3.6 Demo do Checkpoint 2 — roteiro (`src/demo.py`) e ensaio ✅ (5 turnos, números conferidos, 115 s, US$ 0,14;
  transcrição em `docs/demo_checkpoint2.md`); falta apresentar ao vivo (`python src/orchestrator.py --chat`)
  - ✅ Orquestrador (classifica: dados / fora de escopo / ambígua; busca contexto com get_schema/get_metric)
  - ✅ Agente SQL (gera, valida, corrige — máx. 3 erros)
  - ✅ Agente Analista (números, comparações, período, ressalvas detectadas pelo código, próxima pergunta)
- ✅ 3.4 `src/orchestrator.py`: fluxo entre os agentes
- 🔄 3.5 Guardrails
  - ✅ Bloquear INSERT, UPDATE, DELETE, DROP, ALTER (e demais comandos/funções perigosas — no `tools.py`)
  - ✅ LIMIT padrão e timeout (no `tools.py`)
  - ✅ Recusa educada fora de escopo (D11–D13 no dev: botijão de gás, "apague a tabela", "mostre a chave")
  - ✅ SQL sempre exibido ao usuário (anexado pelo código; na interface Streamlit também — Etapa 5)
  - ✅ Chave de API só no `.env` (fora do Git; o banco não consegue lê-la — testado)

## 4. Avaliação ✅
- ✅ 4.0 `colunas_chave` do golden set definidas ANTES da 1ª rodada
- ✅ 4.1 `eval/run_eval.py` (roda as 20 perguntas e compara com a referência; cache desligado)
- ✅ 4.2 Métricas — rodada ANTES das correções (23/11)
  - ✅ Acurácia do resultado: 95% (19/20) após revisão manual (comparador: 18/20)
  - ✅ % de SQL válido na 1ª tentativa: 100%
  - ✅ Média de tentativas de correção: 0,00
  - ✅ Tempo médio de resposta: 19,7 s
  - ✅ (opcional) tokens/custo: 714.660 tokens · US$ 0,83
- ✅ 4.3 `eval/analise_erros.md` (falha, causa, correção) — versão "antes"
- ✅ 4.4 Corrigir (camada semântica: R02 posto/CEP; comparador: arredondamento + `--recomparar`) e rodar de novo
- ✅ 4.5 Métricas DEPOIS das correções → `eval/resultados.csv`: 95% (19/20), SQL 1ª 100%, 0,00 correções, 21,5 s, US$ 0,86
  (#1 corrigida; nova falha #8 por conflito R04 × R05; #15 falso negativo revisado)
- ✅ 4.6 Precedência R05 > R04 + D14–D16 no dev (4/4) + 3ª rodada "depois_2": 90% (18/20) — #8 (Orquestrador
  interpreta o período) e #16 (bug de paginação: tabela final com 7 de 27 UFs)
- ✅ 4.7 Bug de paginação + Orquestrador não traduz período (dev 4/4) → rodada **final** (última): 90% (18/20) —
  #8 e #16 corrigidas; novas falhas #14 (LIMIT 1 + Analista) e #19 (armadilha com o luna). 4 rodadas: 95/95/90/90%
- ✅ 4.8 Melhorias sem nova rodada no golden set (Orquestrador → terra; Analista recebe o SQL; comparar todas as
  opções citadas) validadas no dev: 4/4

## 5. Acabamento ✅
- ✅ 5.1 `src/app.py` — interface Streamlit (texto + tabela + SQL usado), testada no navegador
  - ✅ Cabeçalho: título do projeto, curso, matéria, professor; barra lateral: desenvolvedores, fonte ANP, exemplos, modelos, gasto
  - ✅ Conversa com histórico (esclarecimento), progresso por agente, gráfico automático, CSV, detalhes da execução
  - ✅ Logos da Impacta e da ANP (enviados pelo aluno) em `assets/`, no cabeçalho
  - ✅ Visual no estilo do site da Impacta (tema escuro, azul/ciano, Montserrat)
  - ✅ Pedido de esclarecimento explícito ("Preciso de uma informação sua para continuar" + aviso "responda abaixo")
- ✅ 5.2 `README.md`
  - ✅ Como rodar (venv, `load_data.py`, `.env`, `app.py`, CLI e testes)
  - ✅ Diagrama da arquitetura (Mermaid) + tabela dos agentes
  - ✅ Stack e justificativa das escolhas
  - ✅ Link para baixar os dados da ANP
  - ✅ Resumo da avaliação, guardrails, limitações, print da tela
- 🔄 5.3 `USO_DE_IA.md` (atualizar ao longo do projeto; preencher correções manuais)
- ✅ 5.4 Revisar estrutura do repositório (seção 5 do enunciado) — conferida antes do 1º commit (57 arquivos)
- ✅ 5.5 Conferir: nenhuma chave de API no GitHub — `.env` fora, nenhum padrão `sk-...` nos arquivos enviados
- ✅ 5.6 App publicado no Streamlit Community Cloud (pelo aluno): https://iaprecoscombustivel.streamlit.app/
  - ✅ `app.py` lê a chave dos Secrets do Streamlit; `.streamlit/secrets.toml` no `.gitignore`
  - ✅ Aluno colou `OPENAI_API_KEY` em Settings → Secrets e testou online ("funcionou e ficou muito bom")
  - 💡 Projeto futuro (decisão do aluno): senha de acesso e limite de perguntas por sessão
- ✅ 5.7 Ajustes visuais pedidos pelo aluno: pergunta (azul) e resposta (ciano) com borda, fundo e sombra próprios;
  link do LinkedIn no chip do professor e no nome do Jeferson (mesma aparência). Testado no navegador embutido.
  - ✅ Título do professor trocado para "Prof. Dr." no app e no README (decisão do aluno; LinkedIn mostra PhD)
  - ✅ Ordem da resposta: texto → gráfico → tabela (+ CSV) → SQL (pedido do aluno)
  - ✅ Bug corrigido: gráfico de BARRAS nunca aparecia (pandas 3 usa o tipo "str" para texto, não "object");
    testado com o ranking de 5 estados (etanol)
- ✅ 5.8 Seletor de modelos — **descartado** pelo aluno (24/11): a versão 5 (gpt-5.6-terra/sol/luna) custa 2× mais
  e não foi avaliada; ficam só os modelos atuais
- ✅ 5.9 Limite de uso: 20 perguntas por sessão + 500 por dia no app inteiro (contador compartilhado com trava;
  F5 e "Nova conversa" não zeram; pergunta devolvida se a OpenAI falhar; caixa desabilitada ao atingir).
  Testado numa cópia com limites 1 (sessão e dia). `LIMITE_SESSAO`/`LIMITE_DIA` no `.env.example` e README
- ✅ 5.10 Registro das perguntas (`src/registro.py`): data/hora, sessão (id aleatório), IP, navegador, sistema,
  fuso, idioma, localização (~1 km) ou CEP, pergunta, tipo, pergunta interpretada, linhas, SQL 1ª, custo, tempo,
  erro — SEM nome da máquina e SEM geolocalização pelo IP (decisão do aluno); em segundo plano; aviso LGPD no app
- ✅ 5.11 Planilha Google (gspread + conta de serviço; credencial em `.streamlit/secrets.toml`, fora do Git;
  reserva em `logs/perguntas.csv`). Testado: cabeçalho criado e a pergunta "álcool em Floripa" registrada.
  ⚠️ Aluno: colar `[registro]` e `[gcp_service_account]` também nos Secrets do Streamlit Cloud
- ✅ 5.12 Base atualizada com os **relatórios semanais** da ANP (aluno baixou 21 .xlsx, 28/06 a 21/11/2026)
  - ✅ Exploração: cabeçalho na linha 10 nos 21 arquivos; 7 diferenças de formato mapeadas (CNPJ/CEP numéricos,
    estado por extenso, sem região, nomes de produto, GLP, colunas extras)
  - ✅ Validação: 11.472 coletas de 29–30/06 iguais nos 2 formatos (100%) → semanal descarta datas ≤ 30/06
  - ✅ `load_data.py`: `ler_semanal()` + 2 testes CRÍTICOS novos (UF, produto) + `--sem-semanal`; 345.314 linhas
    novas; base 01/01/2020 a 21/11/2026 (5.809.204 linhas); histórico até 30/06 idêntico
  - ✅ Testes: qualidade (17), camada semântica, tools, golden set; app conferido com SQL independente
  - ✅ YAML, README, app e `docs/qualidade_dados.md` atualizados; `openpyxl` no requirements
- 🔄 5.13 Postos próximos ao usuário (complemento — fora da entrega de validação; só SP primeiro; Google Geocoding)
  - ✅ Cota conferida: 1.978 postos ativos de SP ≈ 20% das 10 mil consultas grátis/mês (limite do aluno: 50%)
  - ✅ Tutorial da chave: projeto separado, restrição à Geocoding API, limite diário, alerta de orçamento, Secrets
  - ✅ 5.13a Rua e número na `dim_posto` (antes descartados); fato idêntica; todos os testes ✅
  - ✅ Chave do Google testada (1 consulta: MASP na coordenada certa; outra API recusada)
  - ✅ 5.13b `geocodificar_postos.py` (cache com retomada, teto, validação do município, nova tentativa em falha
    de rede — a 1ª carga caiu no posto 512 com WinError 10054) + colunas `latitude`, `longitude`, `precisao_geo`,
    `geocodificado_em` na `dim_posto` + 3 testes de qualidade (informativo, fora do Brasil, > 30 dias).
    Piloto 20/20 no município certo (13 ROOFTOP, 7 centro da rua)
  - ✅ 5.13c YAML: métrica `distancia_km` (haversine) + R15 + checklist + ressalva "distancia"; agentes: o app
    informa ao Orquestrador SE há localização (mensagem developer) e o CÓDIGO entrega lat/lon ao Agente SQL
  - ✅ 5.13d App: botão "📍 Usar minha localização" (streamlit-js-eval) + CEP (`src/geo.py`, Google, só os 8
    dígitos) + aviso de privacidade + pergunta de exemplo. Testado: CEP 01310-200 → 4 postos no raio de 3 km
    (= SQL direto); sem raio → pergunta a distância; sem localização → pede botão/CEP. Regressão dev 5/5 ✅
  - ⚠️ Aluno: apagar/refazer as coordenadas até ~25/12/2026 (termos do Google); baixar o limite diário para 200;
    colar `GOOGLE_MAPS_API_KEY` nos Secrets do Streamlit
  - ✅ 5.13e Ajustes pedidos pelo aluno: localização + CEP + exemplo num painel "📍 Localização" AO LADO da caixa de
    pergunta (rodapé `st._bottom` + popover; botões com callbacks); desenvolvedores com Jeferson primeiro e letra
    maior; link da graduação no chip do curso; título menor em telas estreitas. Testado (CEP → exemplo → R$ 5,79).
    Aluno ativou a Routes API para o futuro (a chave atual continua restrita à Geocoding)
  - ✅ 5.13f (aprovado e commitado) Layout: título em 1 linha com degradê/brilho e barra;
    logos na linha dos chips; faixa de apresentação neutra; área central 1.480 px; cards mais baixos; exemplos no
    centro (5 botões, mesma altura); caixa de pergunta em destaque com a mesma altura do botão Localização (76 px)
  - ✅ 5.13g (aprovado e commitado) R15 com **raio automático**: sem raio -> 3 km; nada -> 5 km (mesma
    consulta, coluna raio_km); nada até 5 km -> avisa e pergunta se busca até 10 km. Testado com os 3 agentes:
    MASP (3 km), Cantareira B (ampliou p/ 5 km), Serra da Cantareira (0 → pergunta 10 km → "sim" → 10 postos)
  - ✅ 5.13i (aprovado e commitado) 1º exemplo trocado por "Qual é o preço mais recente da gasolina do
    posto mais próximo a mim?" + R15 ("o mais próximo" ordena pela distância, preço da última coleta — R02);
    testado no app (Av. Paulista: José Maria Lisboa, 0,76 km, R$ 7,79 em 16/11 = SQL independente). Cabeçalho
    FIXO só em telas ≥ 900 px (no celular rola normalmente) — testado em 1440 px e 375 px
  - ✅ 5.13h (aprovado e commitado) Fonte dos dados semanais ("Levantamento de Preços — últimas semanas
    pesquisadas", ANP) citada na barra lateral do app e no README, ao lado da Série Histórica

## 6. Apresentação ✅ (material pronto; falta só apresentar)
- ✅ 6.1 Estrutura aprovada (aluno, 24/11): 15 min, só o Jeferson apresenta, slides + roteiro, 8 blocos, demo de 5
  perguntas (ranking, série, ambiguidade, posto mais próximo, ataque) + reservas
- ✅ 6.2 Roteiro escrito: `docs/roteiro_apresentacao.md` (falas-guia por bloco, demo, checklist, plano B)
- ✅ 6.3 Slides (9, visual do app, notas do apresentador): https://claude.ai/artifact/5RFFZheTRgtYnG9LaSQqQU —
  conferidos numa pré-visualização local; aprovados pelo aluno
- ✅ 6.4 `docs/perguntas_banca.md`: 27 perguntas prováveis em 8 temas (aprovado)
- ✅ 6.5 Ensaio (24/11, app local, CEP 01310-200): as 5 perguntas funcionaram, números conferidos com SQL independente
  (P2: tabela exata, texto com 1 imprecisão — pico em março); tempos 24–48 s (espera total ~3 min 45 s), US$ 0,27.
  `docs/demo_apresentacao.md` + 8 prints em `docs/imagens/demo/`; roteiro corrigido (digitar a partir da P2, tempos
  reais, pular P2 se atrasar) — aprovado e commitado
- ⬜ Apresentar (aluno), seguindo o checklist da véspera e do dia no roteiro

## 7. Ajustes de uso (feedback de usuário, 24/11) ✅
- ✅ 7.1 (aprovado e commitado) Um usuário não percebeu o pedido de esclarecimento ("menor preço na região da
  Berrini") e não continuou. Correções no `app.py`:
  - rolagem automática até a pergunta enviada e até o início da resposta (no celular a tela ficava parada);
  - esclarecimento em quadro laranja com letra maior + caixa de pergunta com "✍️ Responda aqui…" piscando em laranja;
  - celular (≤ 640 px): caixa e Localização lado a lado e com a mesma altura; rodapé de 311 → 154 px (38% → 19%);
  - placeholder mais curto ("Pergunte sobre preços…").
  Testado no celular (375 px) e no notebook (1440 px), incluindo o fluxo completo da Berrini.
  - ✅ Regra decidida pelo aluno: "menor/maior preço" e "posto mais barato/caro" SEM período = janela de coleta
    recente (R06), nunca a história toda (YAML: R06, sinônimos, checklist). Testado: Brooklin → R$ 5,99 em
    17/11/2026 (antes: R$ 4,269 de 2020). Golden set e dev não mudam (as perguntas deles têm período).
  - 💡 Limite visto: bairro/“região” depende do nome escrito na base (BROOKLIN × BROOKLIN PAULISTA)
- ✅ 7.2 Teclado do celular fecha ao enviar a pergunta (blur na caixa só em tela de toque — Android e iPhone;
  no notebook o foco fica). Testado na simulação de celular (TEXTAREA → BODY) e no notebook (foco mantido);
  ⚠️ falta o aluno confirmar num iPhone/Android de verdade (a simulação não tem teclado virtual)
- ⬜ Demo ao vivo (com perguntas de reserva)
- ⬜ Todos os membros sabem explicar qualquer parte do projeto

---

## Decisões e ressalvas registradas
- Base ANP, 2020.01 a 2026.01; "Valor de Compra" descartada.
- Bandeira fica na fato (o posto pode trocar de bandeira ao longo do tempo) — confirmado: 3.322 postos trocaram de bandeira e 16 de município.
- Banco DuckDB (~40 MB) pode ir para o GitHub; também é recriável com `python src/load_data.py`. CSVs brutos ficam fora (link no README).
- Set/2020 sem coleta — hipótese: pandemia (a confirmar).
- Pesquisa da ANP é por amostra de postos → ressalva nas respostas do Agente Analista.
- Preço médio = média por posto (cada posto pesa igual). Mínimo, máximo e amplitude usam as coletas (preços reais).
- Datas relativas pela última data da base (30/06/2026), nunca CURRENT_DATE (R01). Coleta antiga → avisar (R07).
- Termos ambíguos (São Paulo, Rio de Janeiro, POA, SP, Rio Branco, Valença, SE) → pedir esclarecimento; bons candidatos às 2 perguntas-armadilha do golden set.
