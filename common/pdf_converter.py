"""Converts DOCX resumes to clean, universally readable PDFs via macOS textutil and Playwright."""

import subprocess
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright


def _render_html_to_pdf(html_path: str, pdf_path: str):
    """Subprocess renderer to avoid Playwright sync loop conflicts."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file://{html_path}")
        page.pdf(
            path=str(pdf_path),
            format="A4",
            margin={"top": "0.4in", "bottom": "0.4in", "left": "0.4in", "right": "0.4in"},
            print_background=True,
        )
        browser.close()


def convert_docx_to_pdf(docx_path: str) -> str:
    """Converts a DOCX resume file into a pixel-perfect PDF file."""
    docx_file = Path(docx_path).resolve()
    if not docx_file.exists():
        raise FileNotFoundError(f"DOCX file not found: {docx_file}")

    html_file = docx_file.with_suffix(".html")
    pdf_file = docx_file.with_suffix(".pdf")

    # 1. Convert docx to html via macOS textutil
    subprocess.run(
        ["textutil", "-convert", "html", str(docx_file), "-output", str(html_file)],
        check=True,
        capture_output=True,
    )

    # 2. Render html to PDF via isolated subprocess
    code = (
        f"from common.pdf_converter import _render_html_to_pdf; "
        f"_render_html_to_pdf({str(html_file)!r}, {str(pdf_file)!r})"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Playwright PDF rendering failed: {res.stderr}")

    # Remove temporary HTML file
    if html_file.exists():
        html_file.unlink()

    return str(pdf_file)
