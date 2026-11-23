# 1.7 — As 10 perguntas de negócio (Checkpoint 1)

> Foco: o usuário consulta **preço por atributo** (local, CEP, produto, bandeira, período, posto) e faz **comparações**.
> Perguntas 1–4: propostas pelo aluno (ajustadas). Perguntas 5–10: sugeridas para completar.
> Status: versão 1 aprovada pelo aluno em 21/11/2026 (revisar com o grupo).

## Regras de negócio que as perguntas exigem (vão para o `semantic_layer.yaml`)
| Regra | Definição proposta | Por quê |
|---|---|---|
| **Preço atual (posto / CEP)** | preço da **última coleta** daquele posto; sempre informar a data | a ANP não visita todo posto toda semana |
| **Último mês** | "último mês" = **último mês com pesquisa** no recorte filtrado (ex.: último mês em que Curitiba teve coleta) | nem todo local é pesquisado todo mês |
| **Preço atual (município / estado / Brasil)** | média das coletas do **último mês com pesquisa** do recorte | usa o dado mais recente disponível |
| **Rankings entre locais** | todos os locais no **mesmo trimestre**: o último trimestre com pesquisa na base (hoje: 2º tri/2026, abr–jun) | mesmo período para todos e mais postos na amostra (jun/2026: 405 municípios com ≥ 5 postos; 2º tri/2026: 415) |
| **Sempre informar a data** | toda resposta baseada no "atual"/"último mês" informa a **data da pesquisa**: posto → data da coleta; agregados → mês e intervalo de datas (1ª e última coleta usadas) | transparência: o usuário sabe quão recente é o dado |
| **Coleta recente** | descobrir o **último mês com dados na base** e considerar os **últimos 3 meses** até ele (ex.: abr–jun/2026) | não recomendar posto com preço de anos atrás |
| **Preços fora do padrão** | **não são removidos nem marcados**; o usuário avalia | decisão do grupo |
| **Etanol compensa** | preço etanol ÷ preço gasolina **≤ 0,70**, no mesmo posto e na mesma data de coleta | regra de mercado (rendimento do etanol ≈ 70%) |
| **Amostra mínima em rankings** | só ranquear municípios com **≥ 5 postos** pesquisados no período | evita "município mais caro" com 1 posto só |
| **CEP** | aceitar com ou sem hífen (comparar só os dígitos) | usuário digita de vários jeitos |
| **Gasolina** | "gasolina" = GASOLINA (comum); aditivada só se o usuário pedir | evita misturar produtos |
| **Unidades** | nunca misturar R$/litro com GNV (R$/m³) | comparação inválida |
| **Preço médio** *(22/11/2026)* | **média por posto**: 1º a média de cada posto no período, depois a média dos postos | cada posto pesa igual, não importa quantas vezes foi visitado |

> Versão completa e oficial das regras: `src/semantic_layer.yaml` (seção `regras_de_negocio`, R01–R14).

## As perguntas
| # | Pergunta | O que o sistema precisa fazer | Nível |
|---|---|---|---|
| 1 | Qual é o preço atual da gasolina no CEP 03210-001? | filtro por CEP (dim_posto) + última coleta + informar a data | fácil |
| 2 | Pela regra dos 70%, liste até 10 postos do **município** de São Paulo onde o etanol compensa na coleta mais recente. | etanol e gasolina do mesmo posto/data + razão ≤ 0,70 + top 10 | difícil |
| 3 | Qual município do Brasil tem a maior média de preço atual da gasolina? | média por município no último trimestre com pesquisa + amostra mínima + ranking | médio |
| 4 | Qual município do Brasil tem a menor média de preço atual do etanol? | idem (último trimestre), produto ETANOL, ordem crescente | médio |
| 5 | Qual é o preço médio do diesel S10 no estado do Paraná no último mês com pesquisa? | filtro UF + produto + mês | fácil |
| 6 | Quantos postos foram pesquisados em Curitiba no último mês com pesquisa? | contagem distinta de CNPJ | fácil |
| 7 | Como evoluiu, mês a mês, o preço médio da gasolina no Brasil em 2025? | série temporal (group by ano_mes) | médio |
| 8 | Postos bandeira branca são mais baratos que os de bandeira? Mostre a diferença média da gasolina por região no último mês com pesquisa. | join dim_bandeira + dim_local + comparação | médio |
| 9 | Qual foi a variação % do preço médio da gasolina entre o 1º semestre de 2025 e o 1º semestre de 2026, por estado? | duas agregações + cálculo de % | difícil |
| 10 | Em Belo Horizonte, qual a diferença entre o posto mais caro e o mais barato do etanol no último mês com pesquisa? | MAX − MIN (amplitude) por município | médio |

## Observações (descobertas ao testar na base)
- **P1:** o CEP 03210-001 existe (Trapézio Auto Posto, Vila Alpina), mas a **última coleta é de 12/09/2022**.
  O sistema deve responder com o preço daquela data **e avisar** que é antiga — ótimo exemplo de ressalva.
- **P2:** "São Paulo" é ambíguo (município ou estado?). Ajustado para "município". A versão ambígua pode virar uma
  **pergunta-armadilha** do golden set (o sistema deve pedir esclarecimento).
- **P3/P4:** há municípios com só 2 coletas de gasolina em jun/2026 (ex.: Avaré) → por isso a amostra mínima.
  ✅ Decisão do aluno: rankings entre locais usam o **último trimestre com pesquisa** (mesmo período para todos).
- **P4:** a base tem **um único tipo de álcool** (ETANOL hidratado). "Por tipo do álcool" não existe.
  ✅ Decisão do aluno: opção (a) — "menor média de preço atual do etanol".
