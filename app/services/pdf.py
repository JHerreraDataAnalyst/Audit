from __future__ import annotations

from pathlib import Path

from app.services.storage import OUTPUTS_DIR


async def html_to_pdf(html: str, output_path: Path | None = None) -> Path:
    """Render HTML to PDF using Playwright Chromium.

    Emula media=print antes de exportar para aplicar los mismos estilos
    tipográficos que la vista de impresión / PDF.
    """
    from playwright.async_api import async_playwright

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = OUTPUTS_DIR / "informe.pdf"

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html, wait_until="networkidle")
        await page.emulate_media(media="print")
        await page.pdf(
            path=str(output_path),
            format="A4",
            print_background=True,
            prefer_css_page_size=True,
            margin={"top": "0mm", "right": "0mm", "bottom": "0mm", "left": "0mm"},
        )
        await browser.close()

    return output_path
