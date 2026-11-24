# Perguntas prováveis do professor — com respostas curtas

**Projeto Final — Do BI ao Analista Virtual** · Analista Virtual de Preços de Combustíveis
Grupo: Douglas H. da Silva, Jeferson Stenzel, Leonardo M. L. Rodrigues, Leonardo M. Lima

> Como usar: respostas de 2 a 4 linhas, para **falar**, não ler. Cada uma diz **onde está a prova** no projeto —
> se der tempo, mostre o arquivo ou o teste. Não sabe? "Boa pergunta: o que medimos foi X; isso nós não testamos."

## 1. Arquitetura e agentes

**1. Por que 3 agentes, e não 1 só?**
Papéis diferentes, com contextos menores: o Orquestrador só classifica e busca contexto; o Agente SQL só escreve e
valida SQL; o Analista só redige. Cada um recebe o mínimo de que precisa — menos custo e menos confusão. Começamos
com 1 agente de ponta a ponta (`src/agente_unico.py`) e só depois dividimos, como pede o enunciado.

**2. O que é "tool calling" no projeto?**
O modelo não acessa o banco: ele **pede** uma ferramenta (ex.: `run_sql` com um SQL) e o **nosso código** executa e
devolve o resultado. Ferramentas: `get_schema`, `get_metric` (Orquestrador), `validate_sql`, `run_sql` (Agente SQL).
Ver `src/tools.py` e `src/agents.py`.

**3. Por que modelos diferentes em cada agente?**
O Agente SQL concentra ~91% do custo e da dificuldade, então usa o modelo mais forte (gpt-6.2-sol). Testamos
alternativas no conjunto de **desenvolvimento**: um modelo 4× mais caro empatou com o sol, e o modelo econômico no
Orquestrador falhou numa armadilha — por isso voltamos ao terra. Ver `docs/escolha_modelos.md`.

**4. Por que não usaram LangChain, CrewAI ou outro framework?**
O fluxo é simples (3 etapas) e código próprio deixa cada guardrail **visível e testável**. Usamos a Responses API da
OpenAI diretamente, num único arquivo (`src/llm.py`): trocar de provedor é mudar só ele.

**5. O que acontece se o SQL der erro?**
O erro volta para o Agente SQL como dado; ele corrige e tenta de novo — no máximo **3 erros** por pergunta
(`MAX_ERROS_SQL = 3`). Na avaliação, o SQL foi válido **na 1ª tentativa em 100%** das perguntas que geram SQL
(18 de 18; as 2 armadilhas não geram).

## 2. Camada semântica

**6. O que é a camada semântica e por que ela é "a parte central"?**
É o conhecimento do analista de BI escrito para a IA: tabelas e colunas descritas, 11 métricas, sinônimos e 15 regras
de negócio (`src/semantic_layer.yaml`). Sem ela, a LLM adivinha — por exemplo, faria a média das coletas em vez da
média por posto. **89 verificações** conferem o YAML contra o banco (`tests/testar_camada_semantica.py`).

**7. Dê um exemplo de regra que mudou a resposta.**
R13: preço médio = **média por posto** (um posto visitado 10 vezes não pesa 10 vezes mais). R05: "atual" num ranking
= último trimestre da base, o mesmo período para todos, com no mínimo 5 postos — senão um município com 1 posto
"ganha" o ranking.

**8. Como o sistema sabe que "Floripa" é Florianópolis?**
Pela seção `sinonimos` do YAML (álcool → ETANOL, Floripa → FLORIANOPOLIS/SC, posto BR → VIBRA…). Termos ambíguos
(como "Rio de Janeiro", cidade ou estado) também estão lá: o Orquestrador pergunta em vez de adivinhar.

**9. Por que não usar a data de hoje ("CURRENT_DATE")?**
Porque a base termina em 21/11/2026: "último mês" é o último mês **com dados na base** (R01). O validador bloqueia
funções de relógio no SQL gerado.

## 3. Dados

**10. De onde vêm os dados e como foram tratados?**
ANP — Série Histórica (13 CSVs semestrais) + 21 relatórios semanais (até 21/11/2026), ~5,8 milhões de preços.
Limpeza: codificação por arquivo, linhas vazias, bandeiras renomeadas unificadas, duplicatas tratadas pela média;
modelo estrela no DuckDB e **20 testes de qualidade** na carga (`src/load_data.py`, `docs/qualidade_dados.md`).

**11. Como juntaram dois formatos diferentes (CSV e Excel)?**
Um adaptador converte o Excel para as mesmas colunas do CSV (CNPJ e CEP com zeros, estado → sigla, nomes de produto).
Validação: as 11.472 coletas de 29–30/06 presentes nos dois formatos eram **100% iguais**, e o histórico até 30/06
continuou idêntico.

**12. Por que DuckDB?**
Banco colunar num único arquivo, muito rápido para agregações; e tem parser oficial, árvore da consulta e modo
somente leitura — que usamos nos guardrails.

**13. E os preços estranhos (muito altos ou baixos)?**
Decisão do grupo: **não removemos nem marcamos** (R14) — entram no cálculo e o usuário avalia. O teste de qualidade
confere a faixa plausível (R$ 0,50 a R$ 20).

## 4. Guardrails e segurança

**14. E se a LLM gerar um DELETE ou DROP?**
Não executa: (1) o parser do DuckDB só aceita **um** comando do tipo SELECT; (2) a árvore da consulta só permite as 6
tabelas; (3) a conexão é **somente leitura**, sem acesso a arquivos e com configuração travada — o próprio banco
recusa. **27 ataques** testados e bloqueados (`tests/testar_tools.py`).

**15. E se o usuário tentar um "prompt injection" ("ignore as regras…")?**
A pergunta é tratada como **dado**, nunca como instrução; pedidos de alterar dados ou revelar segredos são
classificados como fora de escopo e **nenhum SQL é gerado**. Mesmo que passasse, o validador e a conexão somente
leitura barrariam. Testado nas perguntas de dev D12 e D13.

**16. Onde ficam as chaves de API?**
No `.env` (fora do Git) e nos Secrets do Streamlit Cloud — nunca no código nem no GitHub. O `.gitignore` protege
esses arquivos e, antes dos envios, conferimos que nenhuma chave aparece nos arquivos do repositório.

**17. Como evitam consultas pesadas?**
LIMIT 100 quando o SQL não traz LIMIT, timeout de 30 s (a consulta é interrompida) e EXPLAIN antes de executar.
No app online: 20 perguntas por sessão e 500 por dia.

## 5. Avaliação

**18. Como montaram o golden set e evitaram o overfitting?**
20 perguntas (7/7/4/2) com SQL de referência **escrito à mão** e critério de acerto definidos **antes** de qualquer
prompt. Os ajustes foram feitos olhando só um **conjunto de desenvolvimento** separado (17 perguntas); o golden set
só mede. Um script confere que nenhuma pergunta dele foi parar no YAML (`eval/conferir_golden_set.py`).

**19. Como decidem se uma resposta acertou?**
O comparador compara os **valores** da resposta com os do SQL de referência, nas colunas-chave definidas antes
(com tolerância de arredondamento). Os casos em que a pergunta admite várias respostas certas foram revisados à mão,
com a justificativa registrada (`eval/resultados.csv`).

**20. Por que a acurácia caiu de 95% para 90%?**
Cada rodada revelou um problema diferente: corrigimos um erro e apareceram outros que estavam escondidos (ex.: a
armadilha "São Paulo" com o modelo econômico). Com 20 perguntas, a incerteza é de **±1–2 perguntas por rodada** —
sistema com LLM não é determinístico. O SQL válido na 1ª tentativa ficou em 100% nas 4 rodadas.

**21. Qual foi o erro mais interessante?**
O **#16**: o agente "paginava" o resultado com OFFSET e o código guardava só a última página — o usuário via 7 de 27
estados. Era bug no **nosso código**, não na IA. Corrigimos e criamos um teste (`eval/analise_erros.md`).

## 6. Custos e desempenho

**22. Quanto custa e quanto demora?**
≈ US$ 0,04–0,07 por pergunta com dados (recusas e esclarecimentos ≈ US$ 0,001–0,005). Tempo: ≈ 20 s em média na
avaliação (23/11); no ensaio da apresentação (24/11) foram 25–50 s — a latência da API varia de um dia para o outro. Todo o desenvolvimento e as 4 rodadas de avaliação custaram menos de US$ 10. Cada chamada é
registrada em `logs/uso_llm.csv`.

**23. Por que demora 20 segundos?**
São várias chamadas encadeadas (Orquestrador, Agente SQL validando e executando, Analista), com raciocínio ligado no
Agente SQL. Trocamos velocidade por acerto; cache de respostas repetidas é um próximo passo.

## 7. Complementos

**24. Como funciona "postos perto de mim"?**
Geocodificamos os 1.978 postos ativos de SP (Google, ~20% da cota gratuita) e calculamos a distância em linha reta no
próprio SQL (fórmula de haversine). A localização do usuário (navegador ou CEP) é entregue pelo **código** ao Agente
SQL — a LLM não consegue inventá-la. Sem raio: 3 km, amplia para 5 km e pergunta sobre 10 km (R15).

**25. E a privacidade (LGPD)?**
O app avisa o que registra: perguntas e dados técnicos (IP, navegador, sistema, fuso) e a localização só aproximada
(~1 km) ou o CEP — sem nome, sem nome da máquina e sem geolocalização pelo IP. A planilha é escrita por uma conta de
serviço que só tem acesso a ela. As coordenadas do Google seguem a regra de 30 dias.

## 8. Uso de IA

**26. Como usaram IA no desenvolvimento?**
Com o Claude Code, para gerar código, documentação e testes, sempre em micro-etapas com revisão e decisões nossas
(regras de negócio, modelos, layout, o que registrar). Tudo está em `USO_DE_IA.md`, incluindo o que precisou ser
corrigido. Os números citados foram conferidos com SQL independente.

**27. O que vocês fariam diferente?**
Montar o conjunto de desenvolvimento **maior** desde o início (os erros vieram de casos que ele não cobria) e medir o
custo por pergunta mais cedo. E testar a ambiguidade com mais perguntas-armadilha.
