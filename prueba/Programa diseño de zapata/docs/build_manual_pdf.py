"""Genera el manual en PDF a partir del HTML del artefacto.

WeasyPrint no es viable en este entorno (requiere bibliotecas GTK/Pango nativas),
así que se usa el motor de impresión de Chrome/Edge en modo headless — el mismo
que emplea Ctrl+P → «Guardar como PDF», pero automatizado.

Uso:
    py docs/build_manual_pdf.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FUENTE = ROOT / "docs" / "manual_usuario.html"
SALIDA = ROOT / "docs" / "Manual de uso - Zapatas E060.pdf"

# Chrome primero: en este equipo Edge devuelve código 0 pero no escribe el PDF.
NAVEGADORES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# Reglas que solo aplican al PDF. El HTML en pantalla no las lleva.
CSS_IMPRESION = """
/* ---------- Preparación para papel ---------- */
@page {
  size: A4;
  margin: 20mm 18mm 18mm 18mm;
}

html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }

body {
  background: var(--surface);
  font-size: 10.5pt;
  line-height: 1.55;
}

/* Una sola columna: el índice lateral pasa a ser una página de contenido */
.shell {
  display: block;
  max-width: none;
  padding: 0;
}

header.mast {
  padding: 0 0 18px;
  margin-bottom: 26px;
  break-after: avoid;
}
h1 { font-size: 27pt; }
.standfirst { font-size: 12pt; max-width: none; }
.mast-meta { font-size: 8.5pt; margin-top: 16px; }

nav.toc {
  position: static;
  margin: 0 0 26px;
  padding: 16px 20px;
  border: 1px solid var(--line);
  border-radius: 5px;
  background: var(--surface-sunk);
  break-inside: avoid;
  break-after: page;
}
nav.toc ol {
  columns: 2;
  column-gap: 32px;
}
nav.toc a {
  color: var(--ink);
  padding: 3px 0;
  break-inside: avoid;
}
nav.toc a:hover { background: none; }

/* Cada sección abre página nueva; la primera va tras el índice */
section {
  break-before: page;
  margin-bottom: 0;
  padding-bottom: 10px;
}
section:first-of-type { break-before: avoid; }

h2 { font-size: 17pt; break-after: avoid; }
h2 .num { font-size: 9pt; }
h3 { font-size: 12pt; margin-top: 22px; break-after: avoid; }
h4 { font-size: 8.5pt; margin-top: 18px; break-after: avoid; }
.section-lede { font-size: 11pt; margin-bottom: 18px; }

p, li { orphans: 3; widows: 3; }
p, ul, ol.body-list { max-width: none; }

/* Nada de estos bloques debe partirse entre páginas */
.tw, .call, .card, .cmd { break-inside: avoid; }
.cards { break-inside: auto; }

.tw { box-shadow: none; }
table { font-size: 9pt; }
th { padding: 6px 9px; font-size: 8pt; }
td { padding: 6px 9px; }

.call { box-shadow: none; padding: 12px 15px; max-width: none; }
.card { box-shadow: none; padding: 11px 14px; }
.card p { font-size: 10pt; }

.cmd { font-size: 9pt; padding: 10px 12px; white-space: pre-wrap; }

.st { font-size: 8pt; }

footer.end {
  break-before: page;
  font-size: 9pt;
  max-width: none;
}

/* Los enlaces internos no aportan nada en papel */
a { color: var(--ink); text-decoration: none; }
"""


def localizar_navegador() -> str:
    for ruta in NAVEGADORES:
        if Path(ruta).exists():
            return ruta
    raise SystemExit(
        "No se encontró Microsoft Edge ni Google Chrome.\n"
        "Alternativa: abra docs/manual_usuario.html en el navegador y use\n"
        "Ctrl+P → «Guardar como PDF»."
    )


def construir_documento(fragmento: str) -> str:
    """El HTML del artefacto es un fragmento; aquí se completa el documento.

    El fragmento trae <title> y <style> antes del contenido: se separan para
    colocar cada parte donde corresponde. Se fuerza el tema claro con
    data-theme="light" para que el PDF no salga en oscuro si el sistema del
    usuario lo está.
    """
    cabecera, _, cuerpo = fragmento.partition("</style>")
    return (
        '<!doctype html>\n<html lang="es" data-theme="light">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"{cabecera}</style>\n"
        f"<style>{CSS_IMPRESION}</style>\n"
        "</head>\n<body>\n"
        f"{cuerpo}\n"
        "</body>\n</html>"
    )


def main() -> None:
    if not FUENTE.exists():
        raise SystemExit(f"No existe {FUENTE}")

    documento = construir_documento(FUENTE.read_text(encoding="utf-8"))
    navegador = localizar_navegador()

    # Se trabaja en una carpeta temporal de ruta ASCII: el navegador headless
    # tropieza con rutas que llevan espacios y tildes.
    with tempfile.TemporaryDirectory(prefix="manual_pdf_") as tmp:
        tmp_dir = Path(tmp)
        html_tmp = tmp_dir / "manual.html"
        pdf_tmp = tmp_dir / "manual.pdf"
        html_tmp.write_text(documento, encoding="utf-8")

        comando = [
            navegador,
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=10000",
            f"--print-to-pdf={pdf_tmp}",
            html_tmp.as_uri(),
        ]
        print(f"Navegador: {Path(navegador).name}")
        resultado = subprocess.run(comando, capture_output=True, text=True, timeout=180)

        if not pdf_tmp.exists():
            print(resultado.stdout[-2000:])
            print(resultado.stderr[-2000:], file=sys.stderr)
            raise SystemExit("El navegador no generó el PDF.")

        SALIDA.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf_tmp, SALIDA)

    print(f"PDF generado: {SALIDA}")
    print(f"Tamaño: {SALIDA.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
