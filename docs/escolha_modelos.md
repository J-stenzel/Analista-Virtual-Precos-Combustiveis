# Escolha dos modelos por agente (Etapa 3.3b — 23/11/2026)

> Medição feita nas **perguntas de DESENVOLVIMENTO** (`eval/perguntas_dev.csv`), nunca no golden set.
> Provedor: OpenAI (Responses API). Preços por 1M tokens (entrada / cache / saída), consultados em 23/11/2026:
> gpt-6.2-astra 8,00 / 0,40 / 40,00 · gpt-6.2-sol 2,00 / 0,10 / 10,00 · gpt-6.1-terra 1,00 / 0,05 / 5,00 · gpt-6-luna 0,10 / 0,01 / 0,50.

## 1. Agente SQL — gpt-6.2-sol × gpt-6.2-astra (9 perguntas de dados, D1–D9)

| Modelo | Acerto | SQL válido na 1ª | Custo médio do Agente SQL por pergunta | Tempo médio do Agente SQL |
|---|---|---|---|---|
| **gpt-6.2-sol** (escolhido) | 9/9 | 9/9 | **US$ 0,045** | 12,0 s |
| gpt-6.2-astra | 9/9 | 9/9 | US$ 0,187 (**4,2×**) | 11,6 s |

**Conclusão:** o astra não acertou mais nem foi mais rápido; custa 4,2× mais. Fica o **sol**.

## 2. Orquestrador — gpt-6.1-terra × gpt-6-luna (13 perguntas, só classificação e contexto)

| Modelo | Classe correta | Métrica-chave no contexto | Custo total (13 perguntas) | Tempo médio |
|---|---|---|---|---|
| **gpt-6.1-terra** (configuração final) | 13/13 | 13/13 | US$ 0,035 | 6,5 s |
| gpt-6-luna (usado nas 4 rodadas da Etapa 4) | 13/13 | 13/13 | US$ 0,005 | 4,1 s |

Observação: no D10 (Valença, ambígua) o luna buscou esquema e métricas antes de pedir esclarecimento (trabalho
desnecessário, sem erro). **Conclusão:** empate na qualidade medida; o luna economiza ~US$ 0,002 por pergunta
(~6% do custo total) e ~2,4 s no tempo médio. A recomendação da IA era manter o terra por cautela (só 1 caso
ambíguo no dev); **o aluno decidiu trocar para o luna** (mesma qualidade medida, mais barato e mais rápido).
Ponto de atenção para a Etapa 4: conferir as 2 armadilhas do golden set; se o luna falhar nelas, voltar ao terra
(1 linha no `.env`).

**Atualização (Etapa 4, rodada "final"):** o luna falhou na armadilha #19 ("São Paulo" — assumiu o município em
vez de pedir esclarecimento), depois de passar nas 3 rodadas anteriores. Cumprindo a condição combinada, **o
Orquestrador voltou ao gpt-6.1-terra** (decisão do aluno). Validação no dev: D10 e D11 (armadilhas) ✅.

## 3. Agente Analista — gpt-6-luna

Só redige o texto a partir da tabela e das ressalvas detectadas pelo código; respostas adequadas em todas as
perguntas de dev; ~0,2% do custo. Mantido o **luna**.

## Configuração final (`.env`)

| Agente | Modelo | Esforço de raciocínio | Parte do custo |
|---|---|---|---|
| Orquestrador | gpt-6.1-terra | low | ~9% |
| Agente SQL | gpt-6.2-sol | medium | ~91% |
| Agente Analista | gpt-6-luna | low | ~0,2% |

Custo médio medido: **~US$ 0,03–0,04 por pergunta**; tempo médio ~20 s (golden set, Etapa 4).
Gasto total do projeto até esta medição: ~US$ 3,17 (dos US$ 10 de crédito).
