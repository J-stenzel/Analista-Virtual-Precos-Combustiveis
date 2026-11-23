"""Gera um PDF de entrega a partir de um HTML no layout do enunciado.

Uso:  python docs/templates/gerar_pdf.py docs/etapa2.html docs/Etapa2_Preparacao_e_Modelagem.pdf

Dois motores, nesta ordem:
  1. WeasyPrint (se estiver instalado; no Linux é o mais simples: pip install weasyprint)
  2. Microsoft Edge em modo headless (já vem no Windows). A fonte DejaVu Sans do layout
     não vem no Windows, então ela é EMBUTIDA a partir dos arquivos que o pacote
     matplotlib instala (pip install matplotlib).
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def fontes_dejavu_css():
    """@font-face apontando para as fontes DejaVu que vêm com o matplotlib."""
    import matplotlib
    pasta = Path(matplotlib.__file__).parent / "mpl-data" / "fonts" / "ttf"
    fontes = [("DejaVu Sans", "DejaVuSans.ttf", "normal", "normal"),
              ("DejaVu Sans", "DejaVuSans-Bold.ttf", "bold", "normal"),
              ("DejaVu Sans", "DejaVuSans-Oblique.ttf", "normal", "italic"),
              ("DejaVu Sans", "DejaVuSans-BoldOblique.ttf", "bold", "italic"),
              ("DejaVu Sans Mono", "DejaVuSansMono.ttf", "normal", "normal"),
              ("DejaVu Sans Mono", "DejaVuSansMono-Bold.ttf", "bold", "normal")]
    regras = [f'@font-face {{ font-family: "{familia}"; src: url("{(pasta / arquivo).as_uri()}"); '
              f'font-weight: {peso}; font-style: {estilo}; }}'
              for familia, arquivo, peso, estilo in fontes]
    return "<style>\n" + "\n".join(regras) + "\n</style>\n"


def achar_edge():
    candidatos = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                  r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                  shutil.which("msedge"), shutil.which("google-chrome"), shutil.which("chromium")]
    for c in candidatos:
        if c and Path(c).exists():
            return c
    sys.exit("Nem WeasyPrint nem Edge/Chrome encontrados.")


def gerar_com_edge(origem: Path, destino: Path):
    # Cópia temporária do HTML, NA MESMA PASTA (para caminhos relativos funcionarem), com as fontes embutidas
    html = origem.read_text(encoding="utf-8").replace("</head>", fontes_dejavu_css() + "</head>", 1)
    with tempfile.NamedTemporaryFile("w", suffix=".html", dir=origem.parent, delete=False, encoding="utf-8") as tmp:
        tmp.write(html)
        temporario = Path(tmp.name)
    try:
        with tempfile.TemporaryDirectory() as perfil:      # perfil limpo: não mexe no Edge do usuário
            subprocess.run([achar_edge(), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                            f"--user-data-dir={perfil}", f"--print-to-pdf={destino}", temporario.as_uri()],
                           check=True, timeout=120, capture_output=True)
    finally:
        temporario.unlink(missing_ok=True)


if __name__ == "__main__":
    origem, destino = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    try:
        from weasyprint import HTML
        HTML(str(origem)).write_pdf(str(destino))
        motor = "WeasyPrint"
    except (ImportError, OSError):                          # OSError: WeasyPrint sem as bibliotecas GTK no Windows
        gerar_com_edge(origem, destino)
        motor = "Edge headless + DejaVu do matplotlib"
    print(f"PDF gerado ({motor}): {destino}")
