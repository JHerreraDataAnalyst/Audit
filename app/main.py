from __future__ import annotations

from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.domain.content import ContentBlock
from app.domain.finance import BalanceLine
from app.services.context_builder import build_context
from app.services.excel_import import import_balance_from_excel, write_sample_excel
from app.services.pdf import html_to_pdf
from app.services.render import render_report_html, render_ui
from app.services.storage import (
    OUTPUTS_DIR,
    ROOT,
    list_projects,
    load_content,
    load_finance,
    load_project,
    save_content,
    save_finance,
)

STATIC_DIR = Path(__file__).parent / "static"
SAMPLES_DIR = ROOT / "samples"

app = FastAPI(title="Motor de informes financieros", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _flash_redirect(url: str, message: str, kind: str = "ok") -> RedirectResponse:
    sep = "&" if "?" in url else "?"
    return RedirectResponse(
        url=f"{url}{sep}flash={quote(message)}&flash_type={kind}",
        status_code=303,
    )


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    projects = []
    for pid in list_projects():
        try:
            projects.append(load_project(pid))
        except Exception:
            continue
    flash = request.query_params.get("flash")
    flash_type = request.query_params.get("flash_type", "ok")
    html = render_ui("dashboard.html", projects=projects, flash=flash, flash_type=flash_type)
    return HTMLResponse(html)


@app.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_page(
    project_id: str,
    request: Request,
    tab: Annotated[str, Query()] = "datos",
) -> HTMLResponse:
    try:
        project = load_project(project_id)
        finance = load_finance(project_id)
        content = load_content(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado") from exc

    ctx = build_context(project, finance, content)
    html = render_ui(
        "project.html",
        project=project,
        finance=finance,
        content=content,
        validation=ctx["validation"],
        totals=ctx["totals"],
        tab=tab,
        flash=request.query_params.get("flash"),
        flash_type=request.query_params.get("flash_type", "ok"),
    )
    return HTMLResponse(html)


@app.post("/projects/{project_id}/finance")
async def update_finance(
    project_id: str,
    id: Annotated[list[str], Form()],
    label: Annotated[list[str], Form()],
    level: Annotated[list[int], Form()],
    section: Annotated[list[str], Form()],
    role: Annotated[list[str], Form()],
    note_refs: Annotated[list[str], Form()],
    n: Annotated[list[float], Form()],
    n1: Annotated[list[float], Form()],
) -> RedirectResponse:
    finance = load_finance(project_id)
    lines: list[BalanceLine] = []
    for i, line_id in enumerate(id):
        notes_raw = note_refs[i] if i < len(note_refs) else ""
        notes = [p.strip() for p in notes_raw.replace(",", ";").split(";") if p.strip()]
        lines.append(
            BalanceLine(
                id=line_id,
                label=label[i],
                level=level[i],
                section=section[i],  # type: ignore[arg-type]
                role=role[i],  # type: ignore[arg-type]
                note_refs=notes,
                n=n[i],
                n1=n1[i],
            )
        )
    finance.statements.balance.lines = lines
    save_finance(project_id, finance)
    return _flash_redirect(f"/projects/{project_id}?tab=datos", "Cifras guardadas.")


@app.post("/projects/{project_id}/finance/add-row")
async def add_finance_row(
    project_id: str,
    id: Annotated[str, Form()],
    label: Annotated[str, Form()],
    level: Annotated[int, Form()] = 1,
    section: Annotated[str, Form()] = "asset",
    role: Annotated[str, Form()] = "detail",
    note_refs: Annotated[str, Form()] = "",
    n: Annotated[float, Form()] = 0.0,
    n1: Annotated[float, Form()] = 0.0,
) -> RedirectResponse:
    finance = load_finance(project_id)
    if any(ln.id == id for ln in finance.statements.balance.lines):
        return _flash_redirect(
            f"/projects/{project_id}?tab=datos",
            f"Ya existe una línea con id '{id}'.",
            "error",
        )
    notes = [p.strip() for p in note_refs.replace(",", ";").split(";") if p.strip()]
    # Insert before TOTAL ACTIVO if adding to assets, else before last equity total
    new_line = BalanceLine(
        id=id,
        label=label,
        level=level,
        section=section,  # type: ignore[arg-type]
        role=role,  # type: ignore[arg-type]
        note_refs=notes,
        n=n,
        n1=n1,
    )
    lines = list(finance.statements.balance.lines)
    insert_at = len(lines)
    if section == "asset":
        for i, ln in enumerate(lines):
            if ln.section == "asset" and ln.role == "total":
                insert_at = i
                break
    else:
        for i, ln in enumerate(lines):
            if ln.section == "equity_liability" and ln.role == "total":
                insert_at = i
                break
    lines.insert(insert_at, new_line)
    finance.statements.balance.lines = lines
    save_finance(project_id, finance)
    return _flash_redirect(f"/projects/{project_id}?tab=datos", "Fila añadida.")


@app.post("/projects/{project_id}/facts")
async def update_facts(
    project_id: str,
    fact_key: Annotated[list[str], Form()],
    fact_value: Annotated[list[float], Form()],
) -> RedirectResponse:
    finance = load_finance(project_id)
    for key, value in zip(fact_key, fact_value, strict=False):
        finance.facts[key] = value
    save_finance(project_id, finance)
    return _flash_redirect(f"/projects/{project_id}?tab=datos", "Facts actualizados.")


@app.post("/projects/{project_id}/content/{block_id}")
async def update_content_block(
    project_id: str,
    block_id: str,
    text: Annotated[str, Form()],
) -> RedirectResponse:
    content = load_content(project_id)
    existing = content.get(block_id)
    kind = existing.kind if existing else "paragraph"
    content.upsert(ContentBlock(id=block_id, kind=kind, text=text))
    save_content(project_id, content)
    return _flash_redirect(f"/projects/{project_id}?tab=contenido", "Contenido guardado.")


@app.get("/projects/{project_id}/preview", response_class=HTMLResponse)
async def preview_report(project_id: str) -> HTMLResponse:
    try:
        project = load_project(project_id)
        finance = load_finance(project_id)
        content = load_content(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado") from exc
    html = render_report_html(project, finance, content)
    return HTMLResponse(html)


@app.get("/projects/{project_id}/pdf")
async def download_pdf(project_id: str) -> Response:
    try:
        project = load_project(project_id)
        finance = load_finance(project_id)
        content = load_content(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado") from exc

    html = render_report_html(project, finance, content)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUTS_DIR / f"{project_id}.pdf"
    try:
        await html_to_pdf(html, out)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "No se pudo generar el PDF. ¿Instalaste Playwright Chromium? "
                f"({exc})"
            ),
        ) from exc

    return FileResponse(
        path=out,
        media_type="application/pdf",
        filename=f"{project_id}.pdf",
    )


@app.post("/projects/{project_id}/import-excel")
async def import_excel(project_id: str, file: UploadFile = File(...)) -> RedirectResponse:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        return _flash_redirect(
            f"/projects/{project_id}?tab=excel",
            "Sube un archivo .xlsx",
            "error",
        )
    tmp = OUTPUTS_DIR / f"_upload_{project_id}.xlsx"
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(await file.read())
    try:
        finance = load_finance(project_id)
        finance = import_balance_from_excel(tmp, finance)
        save_finance(project_id, finance)
    except Exception as exc:
        return _flash_redirect(
            f"/projects/{project_id}?tab=excel",
            f"Error al importar: {exc}",
            "error",
        )
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return _flash_redirect(
        f"/projects/{project_id}?tab=datos",
        "Excel importado. Balance actualizado.",
    )


@app.get("/samples/balance_sample.xlsx")
async def sample_excel() -> FileResponse:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    path = SAMPLES_DIR / "balance_sample.xlsx"
    write_sample_excel(path)
    return FileResponse(
        path=path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="balance_sample.xlsx",
    )
