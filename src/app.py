"""
Interface do Analista Virtual de Preços de Combustíveis (Etapa 5 — Streamlit).

Rodar (na raiz do projeto, com o venv ativo):
    streamlit run src/app.py

A interface só APRESENTA: toda a lógica está em orchestrator.responder() (3 agentes + camada semântica).
Cada resposta mostra texto + tabela + SQL usado (exigências do enunciado), o progresso de cada agente,
um gráfico automático quando faz sentido (feito pelo código, sem LLM) e o tempo/custo da resposta.
Visual: identidade inspirada no site da Faculdade Impacta (fundo escuro, azul #116FFF, ciano #00D8FF, Montserrat).
"""
import base64
import datetime
import os
import sys
import threading
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# Streamlit Community Cloud: a chave (e, se quiser, os modelos) fica em "Secrets" — NUNCA no GitHub.
# Copia os Secrets para variáveis de ambiente ANTES de importar o llm.py (que lê os.getenv).
# Localmente não há Secrets: nada acontece e vale o .env, como sempre.
try:
    for _nome, _valor in st.secrets.items():
        if isinstance(_valor, (str, int, float)):
            os.environ.setdefault(_nome, str(_valor))
except Exception:            # sem arquivo de Secrets (uso local): o st.secrets avisa com um erro — é esperado
    pass

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
import llm           # noqa: E402
import orchestrator  # noqa: E402
import geo           # noqa: E402  (CEP -> coordenada, complemento 5.13)
import registro      # noqa: E402  (registro das perguntas na planilha Google, 5.10/5.11)
import uuid          # noqa: E402
from streamlit_js_eval import get_geolocation  # noqa: E402  (localização do navegador, com permissão do usuário)

# ---------------------------------------------------------------------------
# Dados do projeto (cabeçalho e barra lateral)
# ---------------------------------------------------------------------------
PROJETO = "Analista Virtual de Preços de Combustíveis"
SUBTITULO = "Projeto Final — Do BI ao Analista Virtual"
CURSO = "Tecnólogo em Banco de Dados — Faculdade de Tecnologia Impacta"
CURSO_URL = "https://www.impacta.edu.br/graduacoes/banco-de-dados"
MATERIA = "Artificial Intelligence"
PROFESSOR = "Prof. Dr. Cesar Augusto Cardoso Caetano"
PROFESSOR_URL = "https://www.linkedin.com/in/cesaraccaetano/"
# (nome, link do LinkedIn ou None) — o link não muda a aparência do nome
DESENVOLVEDORES = [("Jeferson Stenzel", "https://www.linkedin.com/in/jeferson-stenzel/"),   # versão do Jeferson
                   ("Douglas H. da Silva", None),
                   ("Leonardo M. L. Rodrigues", None),
                   ("Leonardo M. Lima", None)]
FONTE_URL = "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/serie-historica-de-precos-de-combustiveis"
# Relatórios SEMANAIS mais recentes (data/raw_semanal) — complementam a série histórica a partir de jul/2026
FONTE_SEMANAL_URL = ("https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/"
                     "levantamento-de-precos-de-combustiveis-ultimas-semanas-pesquisadas")
LOGO_IMPACTA = RAIZ / "assets" / "logo_impacta.png"
LOGO_ANP = RAIZ / "assets" / "logo_anp.png"
MAX_CARACTERES = 500          # guardrail: evita perguntas enormes (custo)
TURNOS_HISTORICO = 4          # quantos turnos anteriores vão para o Orquestrador
# Limites de uso (protegem os créditos da OpenAI; podem ser trocados nos Secrets/.env sem mexer no código)
LIMITE_SESSAO = int(os.getenv("LIMITE_SESSAO", "20"))   # perguntas por sessão do navegador
LIMITE_DIA = int(os.getenv("LIMITE_DIA", "500"))        # perguntas por dia no app inteiro (todos os visitantes)
FUSO_BRASILIA = datetime.timezone(datetime.timedelta(hours=-3))   # o Brasil não tem mais horário de verão

# Perguntas de exemplo (as da demo — nenhuma é do golden set)
EXEMPLOS = [
    "Qual é o preço mais recente da gasolina do posto mais próximo a mim?",   # R15 + R02 (precisa da localização)
    "Em Santa Catarina, posto sem bandeira é mais barato que posto de bandeira na gasolina?",
    "Qual o preço do GNV no Rio de Janeiro?",
    "Como variou mês a mês o preço médio da gasolina no Paraná em 2025?",
    "Quais os 5 estados com o etanol mais barato atualmente?",
]
# Exemplo do complemento 5.13 (só SP): fica no painel "📍 Localização", ao lado da caixa de pergunta
EXEMPLO_PROXIMOS = "Liste os 10 postos mais próximos de mim com a gasolina mais barata num raio de 3 km"
ETAPAS = {"orquestrador": "🧭 Orquestrador: entendendo a pergunta e buscando o contexto…",
          "sql": "🧮 Agente SQL: escrevendo, validando e executando a consulta…",
          "analista": "✍️ Agente Analista: redigindo a resposta…"}
# Etiqueta e cor de cada tipo de resposta + texto do quadro de progresso quando termina
CLASSES = {"DADOS": ("Resposta com dados", "#00A651", "Resposta pronta"),
           "ESCLARECIMENTO": ("Preciso de um esclarecimento", "#FF8A00", "Preciso de uma informação sua para continuar"),
           "FORA_DE_ESCOPO": ("Fora do escopo da base", "#F44336", "Pergunta fora do escopo da base")}

# ---------------------------------------------------------------------------
# Página e estilo
# ---------------------------------------------------------------------------
st.set_page_config(page_title=PROJETO, page_icon="⛽", layout="wide")


def imagem_base64(caminho: Path) -> str:
    """Imagem local embutida no HTML (o st.markdown não lê arquivos do disco)."""
    return "data:image/png;base64," + base64.b64encode(caminho.read_bytes()).decode() if caminho.exists() else ""


st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800;900&display=swap');
html, body, [class*="css"], .stMarkdown, .stButton button, input, textarea { font-family: 'Montserrat', sans-serif !important; }

/* Topo: espaço para o cabeçalho; barra do Streamlit transparente e sem "Deploy" */
.block-container { padding-top: 3.8rem; max-width: 1480px; }   /* área central mais larga */
[data-testid="stHeader"] { background: transparent; }
.stAppDeployButton, [data-testid="stAppDeployButton"] { display: none; }

/* Barra lateral: tons mais escuros do site da Impacta */
[data-testid="stSidebar"] { background: linear-gradient(180deg, #020D13 0%, #071C23 60%, #0D181D 100%);
    border-right: 1px solid #1B3440; }
[data-testid="stSidebar"] * { color: #E8EEF2; }
[data-testid="stSidebar"] a { color: #00D8FF !important; }
[data-testid="stSidebar"] .stButton button {
    background: transparent; border: 1.5px solid #116FFF; border-radius: 14px; color: #FFFFFF;
    text-align: left; font-size: 0.82rem; font-weight: 600; padding: 6px 14px; }
[data-testid="stSidebar"] .stButton button:hover { background: #116FFF; border-color: #116FFF; }
.lateral-titulo { font-weight: 800; letter-spacing: 1px; font-size: 0.74rem; text-transform: uppercase; color: #00D8FF !important;
    margin: 16px 0 4px 0; }
.lateral-texto { font-size: 0.86rem; line-height: 1.4; color: rgba(255,255,255,.85) !important; }
.lateral-devs { font-size: 0.95rem; line-height: 1.5; }   /* nomes do grupo um pouco maiores */
/* Aviso de privacidade: cor própria (#28596A), mais discreta (pedido do aluno) — vence a cor geral da lateral */
[data-testid="stSidebar"] .aviso-privacidade, [data-testid="stSidebar"] .aviso-privacidade * { color: #28596A !important; }

/* Cabeçalho */
.topo { display: block; margin-bottom: 2px; }                     /* título sozinho, largura inteira */
.topo > div:first-child { width: 100%; }
.linha-info { display: flex; align-items: center; justify-content: space-between; gap: 24px;
    border-bottom: 1px solid #1B3440; padding-bottom: 12px; margin-bottom: 14px; }
.linha-info > div:first-child { flex: 1; min-width: 0; }
/* Cabeçalho FIXO ao rolar a conversa — só em telas largas (no celular ocuparia espaço demais e rola normalmente) */
@media (min-width: 900px) {
    [data-testid="stElementContainer"]:has(.topo) { position: sticky; top: 0; z-index: 50; background: #0D181D;
        padding-top: 8px; box-shadow: 0 10px 18px -12px rgba(0,0,0,.65); }
}
@media (max-width: 900px) { .linha-info { flex-direction: column; align-items: flex-start; } }
.topo > div:first-child { flex: 1; min-width: 0; }
/* Título em UMA linha: tamanho acompanha a largura da tela; "Preços de Combustíveis" em degradê azul -> ciano
   com brilho suave; barra de destaque abaixo */
/* o tamanho da letra acompanha a LARGURA DO ESPAÇO DO TÍTULO (cqi = 1% do container): sempre cabe em 1 linha */
.topo > div:first-child { container-type: inline-size; }
.titulo { color: #FFFFFF; font-size: clamp(1.1rem, 3.5cqi, 2.8rem); font-weight: 900; line-height: 1.1;
    text-transform: uppercase; letter-spacing: 1.5px; white-space: nowrap;
    text-shadow: 0 2px 18px rgba(0,216,255,.18); }
.titulo span { background: linear-gradient(90deg, #116FFF 0%, #0A88F4 40%, #00D8FF 100%);
    -webkit-background-clip: text; background-clip: text; color: transparent;
    filter: drop-shadow(0 0 14px rgba(0,216,255,.35)); }
.barra-titulo { width: 120px; height: 4px; border-radius: 4px; margin: 10px 0 8px 0;
    background: linear-gradient(90deg, #116FFF, #00D8FF); box-shadow: 0 0 12px rgba(0,216,255,.6); }
@media (max-width: 900px) { .titulo { white-space: normal; font-size: 1.45rem; } }
.subtitulo { color: #00D8FF; font-weight: 600; font-size: 1rem; }
.logos { display: flex; align-items: center; gap: 14px; background: #FFFFFF; border-radius: 14px; padding: 8px 14px;
    flex-shrink: 0; }
.logos img.impacta { height: 44px; }
.logos .nome-impacta { color: #1E5A7A; font-weight: 900; letter-spacing: 1px; font-size: 1.05rem; line-height: 1.05; }
.logos .nome-impacta small { display: block; font-weight: 600; font-size: .62rem; letter-spacing: .5px; color: #4A6B7C; }
.logos .sep { width: 1px; height: 40px; background: #D5DEE3; }
.logos img.anp { height: 46px; }
.chips { margin: 6px 0 0 0; }
.chip { display: inline-block; border: 1.5px solid #116FFF; color: #FFFFFF; border-radius: 50px;
    padding: 4px 14px; margin: 4px 8px 4px 0; font-size: 0.80rem; font-weight: 600; background: rgba(17,111,255,.10); }
/* Chip com link (professor): mesma aparência; ao passar o mouse, preenche de azul */
a.chip, a.chip:visited { color: #FFFFFF !important; text-decoration: none !important; transition: background .15s; }
a.chip:hover { background: #116FFF; }
/* Nome com link (desenvolvedor): mesmo formato do texto; sublinha só ao passar o mouse */
[data-testid="stSidebar"] a.link-discreto { color: inherit !important; text-decoration: none; }
[data-testid="stSidebar"] a.link-discreto:hover { text-decoration: underline; }

/* Faixa de destaque e cartões */
/* Faixa de apresentação: neutra (sem degradê forte), para não competir com o título e a caixa de pergunta */
.destaque { background: #10222A; color: rgba(255,255,255,.82); border: 1px solid #1B3440; border-left: 4px solid #00D8FF;
    border-radius: 12px; padding: 12px 20px; font-size: 0.98rem; font-weight: 500; line-height: 1.45; margin-bottom: 14px; }
/* Cartões mais largos (ocupam a área central) e mais baixos */
.cartoes { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 14px; }
.cartao { background: #13252D; border: 1px solid #1B3440; border-radius: 14px; padding: 10px 18px 8px 18px; border-top: 3px solid #116FFF; }
.cartao.ciano { border-top-color: #00D8FF; } .cartao.vermelho { border-top-color: #F44336; }
.cartao h4 { color: #FFFFFF; margin: 0 0 4px 0; padding: 0; font-size: 0.82rem; text-transform: uppercase; letter-spacing: .6px; font-weight: 800; }
.cartao ul { margin: 0; padding-left: 16px; color: rgba(255,255,255,.78); font-size: 0.82rem; line-height: 1.35; }
.cartao li { margin: 0; }
@media (max-width: 900px) { .cartoes { grid-template-columns: 1fr; } }

/* Perguntas de exemplo no centro (botões contornados, mesma altura) */
.exemplos-titulo { font-weight: 800; letter-spacing: 1px; font-size: 0.74rem; text-transform: uppercase; color: #00D8FF;
    margin: 2px 0 6px 0; }
.st-key-exemplos .stButton button { background: rgba(17,111,255,.08); border: 1.5px solid #1B3F66; border-radius: 12px;
    color: #E8EEF2; font-size: 0.84rem; font-weight: 600; min-height: 64px; height: 100%; text-align: left; }
.st-key-exemplos .stButton button p { white-space: normal !important; overflow: visible !important;
    text-overflow: clip !important; line-height: 1.3; }                 /* texto completo, em várias linhas */
/* os 5 botões com a MESMA altura (a do maior texto): a altura 100% passa por toda a cadeia de elementos */
.st-key-exemplos [data-testid="stColumn"] [data-testid="stVerticalBlock"],
.st-key-exemplos [data-testid="stColumn"] [data-testid="stElementContainer"],
.st-key-exemplos .stButton, .st-key-exemplos .stButton button { height: 100%; }
.st-key-exemplos .stButton button:hover { border-color: #00D8FF; background: rgba(0,216,255,.10); color: #FFFFFF; }

/* Caixa de pergunta em destaque e botão "Localização" com a MESMA altura */
[data-testid="stChatInput"] { border: 2px solid #116FFF !important; border-radius: 16px !important; background: #13252D !important;
    box-shadow: 0 0 0 4px rgba(17,111,255,.15), 0 8px 28px rgba(17,111,255,.30); min-height: 76px; }
[data-testid="stChatInput"] textarea { font-size: 1.02rem !important; }
[data-testid="stBottom"] [data-testid="stPopover"] button { min-height: 76px; border: 2px solid #116FFF; border-radius: 16px;
    background: #13252D; font-weight: 700; box-shadow: 0 0 0 4px rgba(17,111,255,.15), 0 8px 28px rgba(17,111,255,.30); }
[data-testid="stBottom"] [data-testid="stPopover"] button:hover { background: #116FFF; }

/* Esclarecimento: a pergunta do analista em destaque + a caixa de texto pisca em laranja (3 vezes) até a resposta */
.pergunta-esclarecer { border: 2px solid #FF8A00; background: rgba(255,138,0,.12); border-radius: 14px;
    padding: 14px 18px; margin: 6px 0 4px 0; font-size: 1.15rem; font-weight: 700; color: #FFFFFF; line-height: 1.4; }
@keyframes pulso-laranja { 0%, 100% { box-shadow: 0 0 0 4px rgba(255,138,0,.15); }
                           50% { box-shadow: 0 0 0 10px rgba(255,138,0,.45); } }
body:has(.aguardando-resposta) [data-testid="stChatInput"] { border-color: #FF8A00 !important;
    animation: pulso-laranja 1.4s ease-in-out 3; box-shadow: 0 0 0 4px rgba(255,138,0,.25); }
.aguardando-resposta { display: none; }
/* O script de rolagem fica num iframe de altura 0: some com o espaço que ele ocuparia */
[data-testid="stElementContainer"]:has(iframe[height="0"]) { display: none; }

/* Celular: caixa de pergunta e botão Localização LADO A LADO e mais baixos (antes ocupavam 38% da tela) */
@media (max-width: 640px) {
    [data-testid="stBottom"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 8px !important;
        align-items: stretch !important; }
    /* o botão acompanha a altura da caixa de pergunta (mesma altura, como no notebook) */
    [data-testid="stBottom"] [data-testid="stColumn"]:last-child [data-testid="stVerticalBlock"],
    [data-testid="stBottom"] [data-testid="stColumn"]:last-child [data-testid="stElementContainer"],
    [data-testid="stBottom"] [data-testid="stColumn"]:last-child [data-testid="stLayoutWrapper"],
    [data-testid="stBottom"] [data-testid="stPopover"], [data-testid="stBottom"] [data-testid="stPopover"] > div,
    [data-testid="stBottom"] [data-testid="stPopover"] button { height: 100% !important; }
    [data-testid="stBottom"] [data-testid="stColumn"]:first-child { flex: 1 1 auto !important; min-width: 0 !important; width: auto !important; }
    [data-testid="stBottom"] [data-testid="stColumn"]:last-child { flex: 0 0 92px !important; min-width: 92px !important; width: 92px !important; }
    [data-testid="stBottom"] [data-testid="stPopover"] button [data-testid="stIconMaterial"] { display: none; }
    [data-testid="stChatInput"] { min-height: 52px; box-shadow: 0 0 0 3px rgba(17,111,255,.15); }
    [data-testid="stChatInput"] > div { padding-left: 12px !important; padding-right: 6px !important; }
    /* texto e botão de enviar na MESMA linha (no padrão do Streamlit o botão fica numa linha de baixo) */
    [data-testid="stChatInput"] > div > div { flex-direction: row !important; align-items: center; }
    [data-testid="stChatInput"] > div > div > div:first-child { flex: 1 1 auto; min-width: 0; }
    [data-testid="stChatInput"] > div > div > div:last-child { flex: 0 0 auto !important; width: auto !important; }
    [data-testid="stChatInput"] textarea { font-size: 0.95rem !important; }
    [data-testid="stBottom"] [data-testid="stPopover"] button { min-height: 52px; padding: 4px 6px;
        box-shadow: 0 0 0 3px rgba(17,111,255,.15); }
    [data-testid="stBottom"] [data-testid="stPopover"] button p { font-size: 0.72rem; white-space: normal; line-height: 1.2;
        overflow-wrap: normal; word-break: keep-all; }
}

/* Mensagens da conversa: pergunta (azul) e resposta (ciano) bem separadas.
   Cada mensagem leva um marcador invisível (.msg-usuario / .msg-analista) e o CSS usa :has() para estilizá-la. */
[data-testid="stChatMessage"] { background: #10222A; border: 1px solid #1B3440; border-radius: 16px; padding: 12px 16px;
    margin-bottom: 10px; }
[data-testid="stChatMessage"]:has(.msg-usuario) {
    background: linear-gradient(100deg, rgba(17,111,255,.28) 0%, rgba(10,136,244,.14) 100%);
    border: 1.5px solid #116FFF; border-left: 6px solid #116FFF; box-shadow: 0 4px 16px rgba(17,111,255,.20); }
[data-testid="stChatMessage"]:has(.msg-usuario) p { color: #FFFFFF; font-weight: 600; font-size: 1.02rem; }
[data-testid="stChatMessage"]:has(.msg-analista) {
    background: #13252D; border: 1.5px solid rgba(0,216,255,.45); border-left: 6px solid #00D8FF;
    box-shadow: 0 4px 18px rgba(0,216,255,.10); }
.msg-usuario, .msg-analista { display: none; }
.classe { display: inline-block; color: #FFFFFF; font-weight: 700; font-size: 0.76rem; border-radius: 50px;
    padding: 3px 12px; margin-bottom: 6px; }
.aviso-esclarecer { border: 1.5px dashed #FF8A00; background: rgba(255,138,0,.10); border-radius: 12px;
    padding: 10px 14px; margin: 8px 0; font-size: 0.92rem; }
.rodape-resposta { color: #8FA6B2; font-size: 0.78rem; margin-top: 4px; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Funções de apresentação
# ---------------------------------------------------------------------------
def texto_seguro(texto: str) -> str:
    """O Streamlit trata '$...$' como fórmula matemática: escapa o cifrão de 'R$'."""
    return (texto or "").replace("$", "\\$")


def grafico_automatico(df: pd.DataFrame) -> None:
    """Gráfico feito pelo CÓDIGO (sem LLM): linha para séries mensais, barras para comparar poucos itens."""
    if df.empty or len(df) < 2:
        return
    numericas = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    preferidas = [c for c in numericas if any(p in c.lower() for p in ("preco", "media", "variacao", "pct", "diferenca", "razao"))]
    metrica = (preferidas or [c for c in numericas if not any(p in c.lower() for p in ("ano", "trimestre", "mes"))] or [None])[0]
    if not metrica:
        return
    tempo = next((c for c in df.columns if c.lower() in ("ano_mes", "mes", "mes_pesquisa")), None)
    if tempo and df[tempo].nunique() == len(df):
        # Linha: eixo Y ajustado à faixa dos dados (zero=False), senão a variação de centavos some
        grafico = alt.Chart(df.sort_values(tempo)).mark_line(point=True, color="#00D8FF", strokeWidth=3).encode(
            x=alt.X(f"{tempo}:O", title=tempo), y=alt.Y(f"{metrica}:Q", scale=alt.Scale(zero=False), title=metrica),
            tooltip=[tempo, metrica])
        st.altair_chart(grafico, use_container_width=True)
        return
    # Coluna de texto com um valor por linha (uf, município, bandeira…). No pandas 3 o texto é "str", não "object".
    categoria = next((c for c in df.columns if (pd.api.types.is_string_dtype(df[c]) or df[c].dtype == object)
                      and df[c].nunique() == len(df)), None)
    if categoria and len(df) <= 30:
        # Barras: eixo começa no zero (o comprimento da barra representa o valor)
        grafico = alt.Chart(df).mark_bar(color="#116FFF", cornerRadiusEnd=4).encode(
            x=alt.X(f"{categoria}:N", sort=None, title=categoria),   # mantém a ordem do SQL (ranking)
            y=alt.Y(f"{metrica}:Q", title=metrica), tooltip=[categoria, metrica])
        st.altair_chart(grafico, use_container_width=True)


MARCA_USUARIO = '<span class="msg-usuario"></span>'      # marcadores para o CSS (ver "Mensagens da conversa")
MARCA_ANALISTA = '<span class="msg-analista"></span>'


def mostrar_pergunta(texto: str) -> None:
    st.markdown(MARCA_USUARIO, unsafe_allow_html=True)
    st.markdown(texto_seguro(texto))


def rolar_ate_ultima_mensagem() -> None:
    """Rola a conversa até o INÍCIO da última mensagem (pergunta recém-enviada ou resposta recém-chegada).
    Sem isso, no celular a tela fica parada e a pessoa não vê a resposta nem um pedido de esclarecimento.
    Script mínimo num iframe invisível: só rola a página (não lê nem altera dados). O comentário com um número
    novo a cada chamada faz o Streamlit executar o script de novo.
    Em tela de TOQUE (celular, Android ou iPhone) também fecha o teclado: tira o foco da caixa de texto (blur), que o
    sistema permite — abrir o teclado sozinho não é permitido, fechar é. Rola só depois que o teclado fecha (no
    iPhone a área visível muda de tamanho). No notebook o foco fica na caixa, para a próxima pergunta."""
    components.html(f"""<!-- {uuid.uuid4().hex} --><script>
      const doc = window.parent.document;
      const toque = window.parent.matchMedia('(pointer: coarse)').matches;
      function fecharTeclado() {{
        const ativo = doc.activeElement;
        if (toque && ativo && ativo.tagName === 'TEXTAREA') ativo.blur();
      }}
      setTimeout(fecharTeclado, 50);
      setTimeout(fecharTeclado, 300);          // de novo, caso o Streamlit devolva o foco à caixa depois do envio
      setTimeout(function () {{
        const msgs = doc.querySelectorAll('[data-testid="stChatMessage"]');
        const area = doc.querySelector('[data-testid="stMain"]');
        if (!msgs.length || !area) return;
        const alvo = msgs[msgs.length - 1];
        // em tela larga o cabeçalho fica fixo no topo: desconta a altura dele
        const cab = window.parent.innerWidth >= 900 ? doc.querySelector('.topo') : null;
        const folga = cab ? cab.closest('[data-testid="stElementContainer"]').offsetHeight + 16 : 12;
        area.scrollBy({{top: alvo.getBoundingClientRect().top - area.getBoundingClientRect().top - folga,
                        behavior: 'smooth'}});
      }}, toque ? 550 : 350);                  // no celular, espera o teclado fechar antes de rolar
    </script>""", height=0)


def mostrar_resposta(res: dict) -> None:
    st.markdown(MARCA_ANALISTA, unsafe_allow_html=True)
    nome, cor, _ = CLASSES.get(res["classe"], (res["classe"], "#5B6B82", ""))
    st.markdown(f'<span class="classe" style="background:{cor}">{nome}</span>', unsafe_allow_html=True)
    if res["classe"] == "ESCLARECIMENTO":
        # Pedido de esclarecimento em DESTAQUE (um usuário não percebeu que precisava responder — 24/11)
        st.markdown(f'<div class="pergunta-esclarecer">❓ {texto_seguro(res["resposta"])}</div>', unsafe_allow_html=True)
        st.markdown('<div class="aviso-esclarecer">👇 <b>Responda na caixa de pergunta, lá embaixo</b> — por exemplo: '
                    '<i>"gasolina"</i>, <i>"o estado"</i> ou <i>"3 km"</i>. Eu lembro da sua pergunta anterior e '
                    'completo a consulta.</div>', unsafe_allow_html=True)
    else:
        st.markdown(texto_seguro(res["resposta"]))
    if res.get("linhas"):
        # Ordem: texto (acima) → gráfico → tabela (+ CSV) → SQL
        df = pd.DataFrame(res["linhas"], columns=res["colunas"])
        grafico_automatico(df)
        st.dataframe(df, hide_index=True)
        st.download_button("⬇️ Baixar tabela (CSV)", df.to_csv(index=False).encode("utf-8-sig"),
                           file_name="resultado.csv", mime="text/csv", key=f"csv_{id(res)}")
        st.markdown("**SQL usado** (somente leitura, validado antes de executar):")
        st.code(res["sql"], language="sql")
    with st.expander("🔎 Detalhes da execução"):
        if res.get("pergunta_completa") and res["classe"] == "DADOS":
            st.markdown(f"**Pergunta interpretada pelo Orquestrador:** {texto_seguro(res['pergunta_completa'])}")
        if res.get("ressalvas"):
            st.markdown("**Ressalvas detectadas pelo sistema:**\n" + "\n".join(f"- {texto_seguro(r)}" for r in res["ressalvas"]))
        if res.get("tentativas_run_sql"):
            st.markdown(f"**Execuções de SQL:** {res['tentativas_run_sql']} · válido na 1ª tentativa: "
                        f"{'sim' if res.get('sql_ok_1a_tentativa') else 'não'}")
        linhas = [f"| {a} | {u['tempo_s']} s | {u['chamadas_llm']} | US\\$ {u['custo_usd']:.4f} |"
                  for a, u in (res.get("uso_por_agente") or {}).items()]
        if linhas:
            st.markdown("| Agente | Tempo | Chamadas à LLM | Custo |\n|---|---|---|---|\n" + "\n".join(linhas))
    st.markdown(f'<div class="rodape-resposta">⏱️ {res["tempo_s"]} s · 💲 US$ {res["uso"]["custo_usd"]:.4f}</div>',
                unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Limite de perguntas: por sessão (st.session_state) + por dia no app inteiro (st.cache_resource)
# ---------------------------------------------------------------------------
@st.cache_resource
def contador_do_dia() -> dict:
    """Contador COMPARTILHADO por todas as sessões: o cache_resource é um único objeto no processo do app.
    Zera na virada do dia (horário de Brasília) e quando o app reinicia."""
    return {"data": None, "total": 0, "trava": threading.Lock()}


def perguntas_hoje() -> int:
    c = contador_do_dia()
    with c["trava"]:
        return c["total"] if c["data"] == datetime.datetime.now(FUSO_BRASILIA).date() else 0


def reservar_pergunta() -> str | None:
    """Conta a pergunta ANTES de chamar a LLM (é ali que se gasta). Devolve None se pode seguir,
    ou a mensagem de bloqueio."""
    if st.session_state.perguntas_feitas >= LIMITE_SESSAO:
        return (f"Você usou as {LIMITE_SESSAO} perguntas desta sessão. Obrigado por testar o analista virtual! "
                "Esse limite protege os créditos do projeto acadêmico.")
    c = contador_do_dia()
    hoje = datetime.datetime.now(FUSO_BRASILIA).date()
    with c["trava"]:                     # duas pessoas perguntando no mesmo instante não "furam" o limite
        if c["data"] != hoje:
            c["data"], c["total"] = hoje, 0
        if c["total"] >= LIMITE_DIA:
            return f"O limite diário de {LIMITE_DIA} perguntas do app foi atingido. Volte amanhã!"
        c["total"] += 1
    st.session_state.perguntas_feitas += 1
    return None


def devolver_pergunta() -> None:
    """A OpenAI deu erro e não houve resposta: a pergunta não conta."""
    c = contador_do_dia()
    with c["trava"]:
        c["total"] = max(0, c["total"] - 1)
    st.session_state.perguntas_feitas = max(0, st.session_state.perguntas_feitas - 1)


def texto_restantes() -> str:
    restam = max(0, LIMITE_SESSAO - st.session_state.perguntas_feitas)
    return f'<div class="lateral-texto">{restam} de {LIMITE_SESSAO} nesta sessão</div>'


# ---------------------------------------------------------------------------
# Estado da sessão
# ---------------------------------------------------------------------------
if "mensagens" not in st.session_state:
    st.session_state.mensagens = []          # [{"papel": "usuario"/"assistente", "texto": str, "res": dict}]
    st.session_state.custo_sessao = 0.0
    st.session_state.pendente = None         # pergunta vinda de um botão de exemplo
st.session_state.setdefault("perguntas_feitas", 0)   # NÃO zera no "Nova conversa" (senão furaria o limite)
st.session_state.setdefault("localizacao", None)     # {"lat", "lon", "fonte", "descricao"} — só nesta sessão
st.session_state.setdefault("pedindo_gps", False)
st.session_state.setdefault("erro_local", None)
st.session_state.setdefault("sessao_id", uuid.uuid4().hex[:8])   # id ALEATÓRIO da sessão (agrupa as perguntas)


def contexto_registro() -> dict:
    """Dados técnicos de acesso para o registro (5.10). IP: o 1º do X-Forwarded-For (atrás do proxy do Streamlit
    Cloud) ou o da conexão. Sem nome da máquina e sem geolocalização pelo IP (decisão do aluno)."""
    cabecalhos = st.context.headers or {}
    ip = (cabecalhos.get("X-Forwarded-For") or "").split(",")[0].strip() or st.context.ip_address
    return {"sessao": st.session_state.sessao_id, "ip": ip, "user_agent": cabecalhos.get("User-Agent"),
            "fuso": st.context.timezone, "idioma": st.context.locale, "localizacao": st.session_state.localizacao}


def credenciais_registro() -> tuple[dict | None, str | None]:
    """Credencial da conta de serviço e link da planilha — SÓ nos Secrets (online) ou .streamlit/secrets.toml (local)."""
    try:
        return dict(st.secrets["gcp_service_account"]), st.secrets["registro"]["planilha_url"]
    except Exception:
        return None, None                                  # sem credencial: o registro vai para logs/perguntas.csv

# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="lateral-titulo">Projeto</div>'
                f'<div class="lateral-texto"><b>{PROJETO}</b><br>{SUBTITULO}</div>', unsafe_allow_html=True)
    nomes = [f'<a class="link-discreto" href="{url}" target="_blank" title="LinkedIn de {nome}">{nome}</a>'
             if url else nome for nome, url in DESENVOLVEDORES]
    st.markdown('<div class="lateral-titulo">Desenvolvedores</div><div class="lateral-texto lateral-devs">'
                + "<br>".join(nomes) + "</div>", unsafe_allow_html=True)
    st.markdown('<div class="lateral-titulo">Fonte dos dados</div>'
                f'<div class="lateral-texto"><a href="{FONTE_URL}" target="_blank">ANP — Série Histórica de Preços '
                'de Combustíveis</a> (jan/2020 a jun/2026)<br>'
                f'<a href="{FONTE_SEMANAL_URL}" target="_blank">ANP — Levantamento de Preços: últimas semanas '
                'pesquisadas</a> (jul a 21/11/2026)<br>amostra de postos</div>', unsafe_allow_html=True)



    st.markdown('<div class="lateral-titulo">Agentes e modelos</div><div class="lateral-texto">'
                f'🧭 Orquestrador: {llm.MODELOS["orquestrador"]}<br>🧮 Agente SQL: {llm.MODELOS["sql"]}<br>'
                f'✍️ Analista: {llm.MODELOS["analista"]}</div>', unsafe_allow_html=True)
    st.markdown('<div class="lateral-titulo">Gasto desta sessão</div>', unsafe_allow_html=True)
    gasto_sessao = st.empty()      # atualizado no lugar depois de cada resposta (sem recarregar a página)
    gasto_sessao.markdown(f'<div class="lateral-texto">US$ {st.session_state.custo_sessao:.4f}</div>',
                          unsafe_allow_html=True)
    st.markdown('<div class="lateral-titulo">Perguntas restantes</div>', unsafe_allow_html=True)
    restantes = st.empty()
    restantes.markdown(texto_restantes(), unsafe_allow_html=True)
    st.write("")
    if st.button("🗑️ Nova conversa", use_container_width=True):   # limpa a conversa, mas não o limite
        st.session_state.mensagens, st.session_state.custo_sessao, st.session_state.pendente = [], 0.0, None
        st.rerun()
    # Aviso de privacidade (LGPD: informar o que é registrado e para quê)
    st.markdown('<div class="lateral-texto aviso-privacidade" style="margin-top:14px"><small>🔒 Para fins acadêmicos, registramos as '
                'perguntas e dados técnicos de acesso (IP, navegador, sistema, fuso e, se usada, a localização '
                'aproximada ou o CEP). Não pedimos nome nem dados pessoais.</small></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Cabeçalho: título do projeto + logos + curso, matéria e professor
# ---------------------------------------------------------------------------
logo_impacta, logo_anp = imagem_base64(LOGO_IMPACTA), imagem_base64(LOGO_ANP)
bloco_logos = (
    '<div class="logos">'
    + (f'<img class="impacta" src="{logo_impacta}" alt="Faculdade Impacta">' if logo_impacta else "")
    + '<div class="nome-impacta">IMPACTA<small>Faculdade de Tecnologia</small></div>'
    + '<div class="sep"></div>'
    + (f'<img class="anp" src="{logo_anp}" alt="ANP — fonte dos dados">' if logo_anp else '<b style="color:#00A651">ANP</b>')
    + "</div>")
# Linha 1: título na largura inteira (assim cabe em 1 linha com letra grande).
# Linha 2: subtítulo + chips (curso, matéria, professor) à esquerda e os logos à direita.
st.markdown(f"""
<div class="topo">
  <div>
    <div class="titulo">Analista Virtual de <span>Preços de Combustíveis</span></div>
    <div class="barra-titulo"></div>
  </div>
</div>
<div class="linha-info">
  <div>
    <div class="subtitulo">{SUBTITULO}</div>
    <div class="chips">
      <a class="chip" href="{CURSO_URL}" target="_blank" title="Página do curso na Impacta">🎓 {CURSO}</a><span class="chip">📘 Matéria: {MATERIA}</span><a class="chip" href="{PROFESSOR_URL}" target="_blank" title="LinkedIn do professor">👨‍🏫 {PROFESSOR}</a>
    </div>
  </div>
  {bloco_logos}
</div>
""", unsafe_allow_html=True)

APRESENTACAO = """
<div class="destaque">Pergunte em português sobre preços de combustíveis no Brasil. Três agentes de IA consultam a
base da ANP com SQL e respondem com texto, tabela e o SQL usado.</div>
<div class="cartoes">
  <div class="cartao"><h4>O que responde</h4><ul>
    <li>Preço médio por município, estado, região ou Brasil</li>
    <li>Preço atual de um posto ou CEP</li>
    <li>Rankings, evolução no tempo e variação %</li>
    <li>Etanol × gasolina (regra dos 70%) e bandeira × posto sem bandeira</li></ul></div>
  <div class="cartao ciano"><h4>Como responde</h4><ul>
    <li>🧭 Orquestrador entende e busca o contexto</li>
    <li>🧮 Agente SQL consulta (somente leitura)</li>
    <li>✍️ Analista explica, com o período e as ressalvas</li>
    <li>Camada semântica com regras de negócio</li></ul></div>
  <div class="cartao vermelho"><h4>O que NÃO faz</h4><ul>
    <li>Não altera nem apaga dados</li>
    <li>Não tem margem, preço de compra nem GLP</li>
    <li>Não cobre todos os postos (é uma amostra da ANP)</li>
    <li>Não prevê preços futuros</li></ul></div>
</div>"""


def mostrar_exemplos() -> None:
    """Perguntas de exemplo no CENTRO da página (antes ficavam na barra lateral). Clicar = enviar a pergunta.
    Ficam ANTES do ponto em que o script lê st.session_state.pendente, então o 'if st.button' simples funciona."""
    st.markdown('<div class="exemplos-titulo">Experimente perguntar</div>', unsafe_allow_html=True)
    with st.container(key="exemplos"):                    # key -> classe CSS "st-key-exemplos" (estilo dos botões)
        for coluna, (i, exemplo) in zip(st.columns(len(EXEMPLOS)), enumerate(EXEMPLOS)):
            with coluna:
                if st.button(exemplo, key=f"ex_{i}", use_container_width=True):
                    st.session_state.pendente = exemplo


if st.session_state.mensagens:
    with st.expander("ℹ️ Sobre o analista virtual e perguntas de exemplo"):
        st.markdown(APRESENTACAO, unsafe_allow_html=True)
        mostrar_exemplos()
else:
    st.markdown(APRESENTACAO, unsafe_allow_html=True)
    mostrar_exemplos()

# ---------------------------------------------------------------------------
# Conversa
# ---------------------------------------------------------------------------
for msg in st.session_state.mensagens:
    with st.chat_message("user" if msg["papel"] == "usuario" else "assistant",
                         avatar="🧑" if msg["papel"] == "usuario" else "⛽"):
        if msg["papel"] == "usuario":
            mostrar_pergunta(msg["texto"])
        else:
            mostrar_resposta(msg["res"])

# A pergunta chega pelo botão de exemplo ou pela caixa de texto (callback ao_enviar, abaixo).
# A caixa é desenhada no FIM do script: assim ela já aparece desabilitada logo depois da última pergunta permitida.
pergunta = st.session_state.pendente
st.session_state.pendente = None
bloqueio = reservar_pergunta() if pergunta else None
if bloqueio:
    st.warning(f"🚦 {bloqueio}")
    pergunta = None
elif pergunta:
    restantes.markdown(texto_restantes(), unsafe_allow_html=True)   # o contador já desconta esta pergunta

if pergunta:
    historico = [{"pergunta": u["texto"], "resposta": a["res"]["resposta"]}
                 for u, a in zip(st.session_state.mensagens[::2], st.session_state.mensagens[1::2])][-TURNOS_HISTORICO:]
    st.session_state.mensagens.append({"papel": "usuario", "texto": pergunta})
    with st.chat_message("user", avatar="🧑"):
        mostrar_pergunta(pergunta)
    rolar_ate_ultima_mensagem()          # mostra a pergunta e o progresso dos agentes (no celular a tela não rolava)
    with st.chat_message("assistant", avatar="⛽"):
        st.markdown(MARCA_ANALISTA, unsafe_allow_html=True)    # já estiliza o quadro enquanto os agentes trabalham
        with st.status("Analisando a pergunta…", expanded=True) as status:
            def ao_etapa(etapa: str) -> None:
                status.update(label=ETAPAS[etapa])
                st.write(ETAPAS[etapa])
            res = None
            try:
                res = orchestrator.responder(pergunta, historico, ao_etapa=ao_etapa,
                                             localizacao=st.session_state.localizacao)
                rotulo = CLASSES.get(res["classe"], ("", "", "Pronto"))[2]
                status.update(label=f"{rotulo} ({res['tempo_s']} s)", state="complete", expanded=False)
            except llm.ErroLLM as erro:
                status.update(label="Não foi possível responder", state="error")
                st.session_state.mensagens.pop()        # tira a pergunta sem resposta do histórico
                devolver_pergunta()                     # e ela não conta no limite
                st.error(f"⚠️ {erro}")
                registro.registrar(registro.montar_linha(contexto_registro(), pergunta, erro=str(erro)),
                                   *credenciais_registro())
        if res:
            mostrar_resposta(res)
    rolar_ate_ultima_mensagem()          # leva a tela ao INÍCIO da resposta (ou do pedido de esclarecimento)
    if res:
        st.session_state.mensagens.append({"papel": "assistente", "texto": res["resposta"], "res": res})
        st.session_state.custo_sessao += res["uso"]["custo_usd"]
        # Registro da pergunta (planilha Google; reserva em CSV) — em segundo plano, não atrasa a resposta
        registro.registrar(registro.montar_linha(contexto_registro(), pergunta, res), *credenciais_registro())
    # Atualiza só o gasto e o contador na barra lateral (um st.rerun() levaria a página de volta ao topo da conversa)
    gasto_sessao.markdown(f'<div class="lateral-texto">US$ {st.session_state.custo_sessao:.4f}</div>',
                          unsafe_allow_html=True)
    restantes.markdown(texto_restantes(), unsafe_allow_html=True)


def ao_enviar() -> None:
    """Callback da caixa de texto: roda ANTES da próxima execução do script e guarda a pergunta digitada."""
    st.session_state.pendente = st.session_state.get("entrada")


fim_sessao = st.session_state.perguntas_feitas >= LIMITE_SESSAO
fim_dia = perguntas_hoje() >= LIMITE_DIA
esgotado = fim_sessao or fim_dia
if esgotado and not bloqueio:
    st.info(f"🚦 Você usou as {LIMITE_SESSAO} perguntas desta sessão. Obrigado por testar o analista virtual!"
            if fim_sessao else f"🚦 O limite diário de {LIMITE_DIA} perguntas do app foi atingido. Volte amanhã!")

# ---------------------------------------------------------------------------
# Localização do usuário (complemento 5.13 — "postos perto de mim", só SP por enquanto).
# Fica num painel ao lado da caixa de pergunta. Os botões usam CALLBACKS (on_click), que rodam ANTES da próxima
# execução do script — como o da caixa de texto —, porque este trecho está no fim do script.
# ---------------------------------------------------------------------------
def _pedir_gps() -> None:
    st.session_state.pedindo_gps, st.session_state.erro_local = True, None


def _usar_cep() -> None:
    r = geo.geocodificar_cep(st.session_state.get("cep_digitado", ""))
    if r["ok"]:
        st.session_state.localizacao = {k: r[k] for k in ("lat", "lon", "fonte", "descricao")}
        st.session_state.erro_local = None
    else:
        st.session_state.erro_local = r["erro"]


def _remover_local() -> None:
    st.session_state.localizacao = None


def _exemplo_proximos() -> None:
    st.session_state.pendente = EXEMPLO_PROXIMOS


if st.session_state.pedindo_gps:                       # o navegador pede permissão; a resposta chega num novo rerun
    gps = get_geolocation(component_key="gps")
    if gps:
        st.session_state.pedindo_gps = False
        coords = gps.get("coords") if isinstance(gps, dict) else None
        if coords and coords.get("latitude") is not None:
            st.session_state.localizacao = {"lat": coords["latitude"], "lon": coords["longitude"],
                                            "fonte": "Localização do navegador",
                                            "descricao": f"precisão ~{round(coords.get('accuracy') or 0)} m"}
        else:
            st.session_state.erro_local = "Não foi possível obter a localização (permissão negada?). Informe um CEP."
        st.rerun()

local = st.session_state.localizacao
# O analista pediu um esclarecimento e espera a resposta? -> a caixa muda o texto e pisca em laranja (CSS :has)
ultima = st.session_state.mensagens[-1] if st.session_state.mensagens else None
aguardando_resposta = bool(ultima and ultima["papel"] == "assistente" and ultima["res"]["classe"] == "ESCLARECIMENTO")
if aguardando_resposta and not esgotado:
    st.markdown('<span class="aguardando-resposta"></span>', unsafe_allow_html=True)
with st._bottom:                                      # rodapé fixo da página, onde fica a caixa de pergunta
    col_pergunta, col_local = st.columns([4, 1.4], vertical_alignment="bottom")
    with col_pergunta:
        st.chat_input("Limite de perguntas atingido." if esgotado else
                      "✍️ Responda aqui…" if aguardando_resposta else
                      "Pergunte sobre preços…",
                      max_chars=MAX_CARACTERES, disabled=esgotado, key="entrada", on_submit=ao_enviar)
    with col_local:
        with st.popover("✅ Localização" if local else "📍 Localização", use_container_width=True):
            st.markdown("**Postos perto de você** · estado de SP")
            if local:
                st.success(f"{local['fonte']}  \n{local.get('descricao', '')}")
                st.button("Remover localização", on_click=_remover_local, use_container_width=True)
            else:
                st.button("📍 Usar minha localização", on_click=_pedir_gps, use_container_width=True)
                with st.form("form_cep", border=False):
                    st.text_input("ou informe um CEP", key="cep_digitado", placeholder="ex.: 01310-200", max_chars=10)
                    st.form_submit_button("Usar este CEP", on_click=_usar_cep, use_container_width=True)
            if st.session_state.get("erro_local"):
                st.warning(st.session_state.erro_local)
            st.markdown("**Experimente:**")
            st.button(f"💬 {EXEMPLO_PROXIMOS}", on_click=_exemplo_proximos, use_container_width=True,
                      disabled=esgotado)
            st.caption("A localização é usada para calcular a distância até os postos (vai na consulta aos "
                       "agentes). No registro de uso fica só aproximada (~1 km) ou o CEP informado.")
