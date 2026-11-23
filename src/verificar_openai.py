"""
Verifica se a chave da OpenAI está configurada e quais modelos ela enxerga — SEM GASTAR créditos.

Rodar a partir da raiz do projeto, com o venv ativo:
    python src/verificar_openai.py

O que faz:
  1. Lê o .env e confere se OPENAI_API_KEY foi preenchida (NUNCA imprime a chave).
  2. Lista os modelos disponíveis para a sua conta (chamada gratuita: não gera tokens).
  3. Confere se os modelos escolhidos para os 3 agentes existem na sua conta.
"""
import os
import sys

from dotenv import load_dotenv
import openai

sys.stdout.reconfigure(encoding="utf-8")   # acentos no terminal do Windows
load_dotenv()                              # lê o arquivo .env da pasta atual

# ---------------------------------------------------------------------------
# 1. A chave existe? (só mostra o começo e o tamanho, nunca a chave inteira)
# ---------------------------------------------------------------------------
chave = os.getenv("OPENAI_API_KEY", "").strip()
if not chave:
    sys.exit("❌ OPENAI_API_KEY está vazia no .env. Cole a chave depois do '=' e salve o arquivo.")
if not chave.startswith("sk-"):
    sys.exit("❌ A chave não começa com 'sk-'. Confira se colou a chave inteira (sem aspas e sem espaços).")
print(f"✅ Chave encontrada no .env (começa com '{chave[:7]}…', {len(chave)} caracteres)")

# ---------------------------------------------------------------------------
# 2. A chave funciona? Listar modelos é gratuito.
# ---------------------------------------------------------------------------
client = openai.OpenAI()   # o SDK lê OPENAI_API_KEY do ambiente
try:
    disponiveis = {m.id for m in client.models.list()}
except openai.AuthenticationError:
    sys.exit("❌ Chave recusada (inválida ou revogada). Crie uma chave nova em platform.openai.com > API keys.")
except openai.PermissionDeniedError:
    sys.exit("❌ A chave não tem permissão para listar modelos. Crie a chave com permissão 'All'.")
except openai.APIConnectionError:
    sys.exit("❌ Sem conexão com a OpenAI. Confira a internet/proxy e tente de novo.")
print(f"✅ Chave aceita pela OpenAI: {len(disponiveis)} modelos disponíveis para a sua conta")

# ---------------------------------------------------------------------------
# 3. Os modelos escolhidos para os agentes existem?
# ---------------------------------------------------------------------------
escolhidos = {
    "Orquestrador": os.getenv("MODELO_ORQUESTRADOR", ""),
    "Agente SQL": os.getenv("MODELO_SQL", ""),
    "Agente Analista": os.getenv("MODELO_ANALISTA", ""),
}
candidatos_teste = ["gpt-6.2-astra", "gpt-6.2-sol", "gpt-6.1-terra", "gpt-6-luna"]   # usados no teste rápido

faltando = False
print("\nModelos dos agentes (.env):")
for agente, modelo in escolhidos.items():
    ok = modelo in disponiveis
    faltando |= not ok
    print(f"  {'✅' if ok else '❌'} {agente:16} {modelo or '(vazio)'}")

print("\nCandidatos do teste rápido:")
for modelo in candidatos_teste:
    print(f"  {'✅' if modelo in disponiveis else '❌'} {modelo}")

if faltando:
    sys.exit("\n⚠️ Algum modelo do .env não está disponível na sua conta: ajuste o nome no .env.")
print("\nTudo pronto para a Etapa 3 ✅  (nenhum crédito foi gasto nesta verificação)")
