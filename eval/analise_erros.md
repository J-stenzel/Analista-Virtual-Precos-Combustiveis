# Análise de erros — Golden set

> Projeto Final "Do BI ao Analista Virtual" · Grupo: Douglas H. da Silva, Jeferson Stenzel, Leonardo M. L. Rodrigues e Leonardo M. Lima
> Golden set: `eval/golden_set.csv` (20 perguntas: 7 fáceis, 7 médias, 4 difíceis, 2 armadilhas), definido **antes** de
> qualquer prompt. Critério de acerto (`colunas_chave`) definido **antes** da 1ª rodada. Resultados: `eval/resultados.csv`;
> respostas, tabelas e SQL de cada pergunta: `eval/detalhes/<rodada>.jsonl`.
> Configuração nas 4 rodadas: Orquestrador gpt-6-luna · Agente SQL gpt-6.2-sol · Agente Analista gpt-6-luna.
> Configuração final entregue: Orquestrador **gpt-6.1-terra** (ver seção 2e e `docs/escolha_modelos.md`).

## 1. Métricas

| Métrica | Antes | Depois | Depois_2 | Final |
|---|---|---|---|---|
| Acurácia | **95% (19/20)** | **95% (19/20)** | **90% (18/20)** | **90% (18/20)** |
| · fáceis / médias / difíceis / armadilhas | 6/7 · 7/7 · 4/4 · 2/2 | 7/7 · 6/7 · 4/4 · 2/2 | 7/7 · 6/7 · 3/4 · 2/2 | 7/7 · 6/7 · 4/4 · 1/2 |
| SQL válido na 1ª tentativa | 100% (18/18) | 100% (18/18) | 100% (18/18) | 100% (18/18) |
| Média de tentativas de correção | 0,00 | 0,00 | 0,06 | 0,00 |
| Tempo médio de resposta | 19,7 s | 21,5 s | 21,3 s | 20,3 s |
| Custo total da rodada (opcional) | US$ 0,83 | US$ 0,86 | US$ 0,90 | US$ 0,91 |
| Tokens totais (opcional) | 714.660 | 738.900 | 762.007 | 772.368 |

Todas as rodadas em 23/11/2026, mesma configuração de modelos e mesmo critério de acerto.
Correções entre rodadas: antes → depois = R02 (posto/CEP) + comparador; depois → depois_2 = precedência R05 > R04;
depois_2 → final = bug de paginação + Orquestrador não traduz expressões de tempo. A rodada "final" foi combinada
como a ÚLTIMA no golden set (para não cair em overfitting).

### Estabilidade por pergunta (só as que falharam alguma vez; as outras 14 acertaram nas 4 rodadas)

| # | Antes | Depois | Depois_2 | Final | Leitura |
|---|---|---|---|---|---|
| 1 | ❌ | ✅ | ✅ | ✅ | corrigida de forma permanente (R02) |
| 8 | ✅ | ❌ | ❌ | ✅ | conflito R04 × R05 + Orquestrador interpretando o período → corrigida |
| 14 | ✅ | ✅ | ✅ | ❌ | nova: LIMIT 1 + Analista sem saber que a consulta era um ranking |
| 15 | ✅ | ✅* | ✅ | ✅ | *falso negativo do comparador (revisão manual) |
| 16 | ✅ | ✅ | ❌ | ✅ | bug de paginação → corrigido |
| 19 | ✅ | ✅ | ✅ | ❌ | nova: armadilha falhou com o Orquestrador gpt-6-luna |

**Conclusão das 4 rodadas:** a acurácia ficou entre 90% e 95% em todas. Cada correção resolveu o erro que
atacou (#1, #8, #16 não voltaram a falhar depois de corrigidos), mas a **variação natural do modelo** fez surgir
outros erros latentes (#14, #19). Com 20 perguntas, a incerteza de uma rodada é de ±1–2 perguntas.

Comparador automático: antes 18/20, depois 18/20. Revisão manual (regra definida antes da 1ª rodada, com
justificativa no `resultados.csv`): antes #18 e depois #15 eram falsos negativos do comparador → 19/20 nas duas.
O comparador foi corrigido (arredondamento) e a rodada "antes" foi **recomparada com a mesma régua** (`--recomparar`).

**Leitura do antes × depois:** a correção funcionou (#1 passou), mas a acurácia ficou igual porque **outra pergunta
(#8) falhou** — e não por causa da correção: o mesmo erro de interpretação já aparecia no "antes", só que lá o
Agente SQL o ignorou. Isso mostra a **variação entre execuções** de um sistema com LLM: a mesma configuração pode
acertar numa rodada e errar na outra. Uma única rodada por configuração mede o desempenho com incerteza de ±1 pergunta.

## 2. Falhas da rodada "antes"

| # | Pergunta | O que aconteceu | Causa (categoria) | Correção | Status |
|---|---|---|---|---|---|
| 1 | Preço atual da gasolina no CEP 03210-001 | Valor certo (R$ 4,94, coleta antiga de 12/09/2022 avisada), mas o Orquestrador reescreveu a pergunta como "preço **médio**" e o Agente SQL fez média entre os postos do CEP em vez de listar a última coleta de cada posto (R02). Só coincidiu porque o CEP tem 1 posto. | **Contexto ambíguo na camada semântica**: os sinônimos mapeavam "preço"/"quanto está" para `preco_medio`, em conflito com a R02 para posto/CEP | Sinônimos: "preço/quanto está" de município/UF/região = média; de **posto ou CEP** = R02 (listar cada posto com a data). R02: "nunca média entre postos do CEP". Validado no dev D4 (CEP com 3 postos) | ✅ corrigido — passou no "depois" |
| 18 | Etanol compensa em Curitiba, mês a mês | Todos os valores corretos; o comparador acusou erro em março porque a referência arredonda o % a 1 casa (5,3) e o agente a 2 (5,33). | **Falso negativo do comparador** (precisão do arredondamento da referência) | Comparador aceita valores que arredondam para o valor da referência (só para valores com casas decimais; contagens continuam exatas). Rodada "antes" recomparada | ✅ corrigido |

## 2b. Falhas da rodada "depois"

| # | Pergunta | O que aconteceu | Causa (categoria) | Correção | Status |
|---|---|---|---|---|---|
| 8 | Município com a maior média de preço atual da gasolina | Município certo (PARINTINS/AM), valor errado: R$ 8,99 (só junho, 7 postos) em vez de R$ 9,062 (2º tri/2026, 9 postos). O Orquestrador escreveu "último mês com pesquisa para cada município" (R04) e o Agente SQL seguiu. | **Conflito entre regras da camada semântica**: R04 ("preço atual" de município = último mês do recorte) × R05 (ranking entre locais = último trimestre da base). O mesmo texto do Orquestrador já aparecia no "antes" — lá o Agente SQL usou o trimestre por conta própria (variação entre execuções) | Proposta: deixar explícita a **precedência** — em rankings/comparações entre locais, "atual" = último trimestre da base (R05 prevalece sobre R04) | ⬜ proposta |
| 15 | Até 10 postos de SP onde o etanol compensa | O agente listou 10 postos em ordem alfabética; a referência lista os 10 de menor razão. | **Falso negativo do comparador** — a pergunta ("até 10 postos onde compensa") admite várias respostas certas (390 postos se qualificam). Conferido: os 10 compensam e usam o par mais recente de cada posto | Revisão manual (acerto). Limitação conhecida do comparador para perguntas com várias respostas válidas | ✅ revisado |

Observações das perguntas que passaram:
- **#13** (ordem das regiões): conferida manualmente — ordem correta (Norte > Nordeste > Sudeste > Centro-Oeste > Sul),
  mesmo com diferença de só R$ 0,007 entre os dois primeiros (o comparador não verifica ordem).
- **#19 / #20** (armadilhas): o Orquestrador (gpt-6-luna) pediu esclarecimento ("São Paulo" cidade ou estado) e recusou a
  margem de lucro, sem executar SQL — confirma a troca terra → luna decidida na Etapa 3.

## 2c. Falhas da rodada "depois_2" (após a precedência R05 > R04, validada em 3 perguntas novas de dev: D14–D16)

| # | Pergunta | O que aconteceu | Causa (categoria) | Correção | Status |
|---|---|---|---|---|---|
| 8 | Município com a maior média de preço atual da gasolina | Falhou de novo (2 de 3 rodadas): o Orquestrador reescreveu "preço atual" como "último mês comum a todos os municípios" (aplicou a cláusula do "último mês" explícito, não o trimestre). | **Desenho do Orquestrador**: ao reescrever a pergunta ele *interpreta o período* com um resumo das regras (sem as exceções) e o Agente SQL — que tem as regras completas — obedece à reescrita. | O Orquestrador NÃO traduz expressões de tempo — repassa as palavras do usuário; o Agente SQL decide o período (validado no dev D14/D15) | ✅ corrigido — passou na "final" |
| 16 | Variação % da gasolina por UF (27 linhas) | O Agente SQL vê só 20 linhas (economia); fez uma 2ª consulta com `OFFSET 20` para ver o resto e o código guardou o ÚLTIMO resultado (7 UFs) como tabela final. | **Bug do sistema** (ferramenta/fluxo), não do modelo — afetaria qualquer usuário | (1) o retorno do `run_sql` avisa que o resultado completo já vai para o usuário; (2) o código não troca a tabela principal por uma consulta com `OFFSET`; (3) `validate_sql` avisa OFFSET (+ teste). Validado no dev D17 (27 linhas) | ✅ corrigido — passou na "final" |

## 2d. Falhas da rodada "final"

| # | Pergunta | O que aconteceu | Causa (categoria) | Correção proposta (sem nova rodada no golden set) |
|---|---|---|---|---|
| 14 | Em 2025, a gasolina foi mais barata nos postos Shell, BR ou Ipiranga? | O Agente SQL trouxe só a vencedora (`LIMIT 1`: RAIZEN R$ 6,24 — que É a mais barata) e o Analista, vendo 1 linha, respondeu que "não é possível determinar". | **Contexto faltando para o Analista**: ele não sabe que a consulta já veio ordenada e cortada (mesmo sintoma visto no dev D14) + o Agente SQL não trouxe as opções citadas pelo usuário | (1) o Analista recebe o SQL executado (como dado) para saber de ordenação/LIMIT; (2) regra no Agente SQL: quando o usuário compara opções que ele mesmo citou, trazer TODAS com seus valores |
| 19 | Qual é o preço médio da gasolina em São Paulo no último mês? (armadilha) | O Orquestrador assumiu o município de São Paulo em vez de perguntar "cidade ou estado?". | **Ambiguidade não detectada** pelo modelo econômico do Orquestrador (gpt-6-luna) — risco registrado em `docs/escolha_modelos.md` ao escolher o luna | Voltar o Orquestrador ao gpt-6.1-terra (condição combinada na escolha do luna) |

## 2e. Melhorias pós-avaliação (aplicadas e validadas só no DEV — sem nova rodada no golden set)

| Falha que motivou | Melhoria (geral) | Validação no dev |
|---|---|---|
| #19 (armadilha com o luna) | Orquestrador de volta ao **gpt-6.1-terra** (condição combinada na escolha do luna) | D10 (Valença) e D11 (botijão) ✅ |
| #14 (Analista e LIMIT 1) | O Analista recebe o **SQL executado** (só para interpretar ordenação/LIMIT); nunca diz "não é possível determinar" por causa de um ranking cortado | D14 ✅ — antes dizia "não é possível confirmar"; agora afirma "ES teve o menor preço" |
| #14 (opções citadas) | `checklist_sql`: quando o usuário compara opções que ele citou, trazer TODAS com seus valores (sem LIMIT 1); e "a última consulta é a resposta completa" | D7 (Ipiranga ou BR) ✅ — as duas bandeiras com valores |

O golden set não foi rodado de novo por decisão do grupo (rodada "final" combinada como a última, para não
ajustar o sistema à prova). A configuração entregue é a de cima (terra / sol / luna).

**Leitura das rodadas:** cada rodada revelou um problema diferente, porque o sistema com LLM **não é
determinístico** — o mesmo erro latente só aparece quando o modelo toma um certo caminho. Iterar
indefinidamente no golden set aproxima-se do *overfitting* que o enunciado proíbe; por isso as correções são
sempre gerais e validadas antes em perguntas de desenvolvimento, e a rodada "final" foi a última.

## 3. Erros encontrados ANTES, nas perguntas de desenvolvimento (não no golden set)

Corrigidos na camada semântica durante a Etapa 3, usando só `eval/perguntas_dev.csv` (sem olhar o golden set):

| Pergunta de dev | Falha | Causa | Correção |
|---|---|---|---|
| D5 (3 estados com GNV mais caro) | Usou o preço MÁXIMO em vez da média | Sinônimo ambíguo: "mais caro" → `preco_maximo` | "Mais caro/barato" entre grupos = preço médio; máx/mín só para preço coletado/posto |
| D8 (5 estados com maior alta) | Excluiu o DF | Ambiguidade: "estados" inclui o DF? | Decisão do grupo: "estados" = 27 UFs com o DF |
| D9 (etanol compensa em Brasília) | 48 postos em vez de 50 | Texto do YAML: "filtrar antes a última data de cada posto" | Montar os pares etanol+gasolina ANTES de pegar a data mais recente |
| D3 (menor preço em Teresina) | Resposta certa marcada como errada | Comparador exigia coluna de contexto | Criada a coluna `colunas_chave` |

**Lição principal:** dos erros reais encontrados (4 no dev + #1, #8, #14, #16 e #19 no golden set), quase todos
vieram de texto ambíguo ou conflitante na **camada semântica** ou do **desenho do fluxo entre agentes**
(Orquestrador interpretando o período; paginação; Analista sem saber da ordenação) e um da **escolha de modelo**
(armadilha com o modelo mais barato) — nenhum de "alucinação" de tabela/coluna: o SQL foi válido na 1ª
tentativa em 100% das perguntas, nas 4 rodadas. A camada semântica é "código" e precisa de testes e revisão como qualquer código.
Os 3 falsos negativos (D3, #18, #15) mostram que o **comparador** também precisa de revisão humana.

## 4. Como as correções são feitas (sem overfitting)

1. Corrigir a **causa geral** (camada semântica, ferramentas ou regras do prompt) — nunca uma regra do tipo
   "se a pergunta for X, responda Y".
2. Validar nas **perguntas de desenvolvimento** e nos testes sem custo (`tests/`), para não piorar nada.
3. Só então rodar a rodada "depois" com o mesmo golden set e o mesmo critério.
