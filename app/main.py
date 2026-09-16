from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from datetime import date

from app.domain.content import ContentBlock, ContentModel
from app.domain.finance import BalanceLine, BalanceStatement, FinanceModel, PygStatement, TableCell
from app.domain.project import Entity, Period, Project
from app.domain.validation import find_concept_impact, validate_all
from app.services.context_builder import build_context
from app.services.excel_import import import_balance_from_excel, write_sample_excel
from app.services.layout_cases import CASES, apply_case
from app.services.pdf import html_to_pdf
from app.services.render import render_report_html, render_ui
from app.services.rollover import rollover
from app.services.storage import (
    OUTPUTS_DIR,
    ROOT,
    list_projects,
    load_content,
    load_content_seed,
    load_finance,
    load_finance_seed,
    load_project,
    project_dir,
    save_content,
    save_finance,
    save_project,
)

STATIC_DIR = Path(__file__).parent / "static"
SAMPLES_DIR = ROOT / "samples"

app = FastAPI(title="Motor de informes financieros", version="0.3.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _flash_redirect(url: str, message: str, kind: str = "ok") -> RedirectResponse:
    sep = "&" if "?" in url else "?"
    return RedirectResponse(
        url=f"{url}{sep}flash={quote(message)}&flash_type={kind}",
        status_code=303,
    )


def _wants_json(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "application/json" in accept


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
        tables_list=ctx["tables_list"],
        tab=tab,
        layout_cases=CASES,
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
    request: Request,
    project_id: str,
    block_id: str,
    text: Annotated[str, Form()],
) -> Response:
    content = load_content(project_id)
    existing = content.get(block_id)
    kind = existing.kind if existing else "paragraph"
    visible = existing.visible if existing else True
    keep = existing.keep_with_next if existing else False
    section = existing.section if existing else ""
    note_number = existing.note_number if existing else None
    table_id = existing.table_id if existing else None
    content.upsert(
        ContentBlock(
            id=block_id,
            kind=kind,
            text=text,
            visible=visible,
            keep_with_next=keep,
            section=section,
            note_number=note_number,
            table_id=table_id,
        )
    )
    save_content(project_id, content)
    if _wants_json(request):
        return JSONResponse({"ok": True, "id": block_id, "action": "update"})
    return _flash_redirect(f"/projects/{project_id}?tab=contenido", "Contenido guardado.")


@app.post("/projects/{project_id}/content/{block_id}/delete")
async def delete_content_block(
    request: Request,
    project_id: str,
    block_id: str,
) -> Response:
    content = load_content(project_id)
    if not content.delete(block_id):
        raise HTTPException(status_code=404, detail="Bloque no encontrado")
    save_content(project_id, content)
    if _wants_json(request):
        return JSONResponse({"ok": True, "id": block_id, "action": "delete"})
    return _flash_redirect(f"/projects/{project_id}?tab=contenido", "Párrafo eliminado.")


@app.post("/projects/{project_id}/content")
async def add_content_block(
    project_id: str,
    text: Annotated[str, Form()],
    after_id: Annotated[str, Form()] = "",
) -> RedirectResponse:
    content = load_content(project_id)
    block = ContentBlock(id=f"narrative.{uuid4().hex[:8]}", kind="paragraph", text=text)
    content.insert_after(after_id or None, block)
    save_content(project_id, content)
    return _flash_redirect(f"/projects/{project_id}?tab=contenido", "Párrafo añadido.")


# ── Table editing endpoints ────────────────────────────────────────────────────

@app.post("/projects/{project_id}/tables/{table_id}")
async def update_table(
    request: Request,
    project_id: str,
    table_id: str,
) -> JSONResponse:
    """Update cells in a generic FinanceTable or Balance statement and return validation."""
    finance = load_finance(project_id)
    body = await request.json()
    cells = body.get("cells", [])

    if table_id in ("balance_asset", "balance_equity"):
        section = "asset" if table_id == "balance_asset" else "equity_liability"
        lines = finance.lines_by_section(section)
        for cell_update in cells:
            row_idx = cell_update.get("row")
            col_id = str(cell_update.get("col", ""))
            line_id = cell_update.get("line_id")
            numeric = cell_update.get("numeric")
            if numeric is None and cell_update.get("value"):
                try:
                    clean_val = cell_update["value"].replace(".", "").replace(",", ".")
                    numeric = float(clean_val)
                except ValueError:
                    pass

            target_line = None
            if line_id:
                target_line = next((ln for ln in finance.statements.balance.lines if ln.id == line_id), None)
            if target_line is None and isinstance(row_idx, int) and 0 <= row_idx < len(lines):
                target_line = lines[row_idx]

            if target_line and numeric is not None:
                if col_id in ("n", "c2", "2"):
                    target_line.n = numeric
                elif col_id in ("n1", "c3", "3"):
                    target_line.n1 = numeric
    elif table_id == "pyg_statement":
        for cell_update in cells:
            row_idx = cell_update.get("row")
            col_id = str(cell_update.get("col", ""))
            line_id = cell_update.get("line_id")
            numeric = cell_update.get("numeric")
            if numeric is None and cell_update.get("value"):
                try:
                    clean_val = cell_update["value"].replace(".", "").replace(",", ".")
                    numeric = float(clean_val)
                except ValueError:
                    pass

            target_line = None
            if line_id:
                target_line = next((ln for ln in finance.statements.pyg.lines if ln.id == line_id), None)
            if target_line is None and isinstance(row_idx, int) and 0 <= row_idx < len(finance.statements.pyg.lines):
                target_line = finance.statements.pyg.lines[row_idx]

            if target_line and numeric is not None and target_line.role != "header":
                if col_id in ("n", "c2", "2"):
                    target_line.n = numeric
                elif col_id in ("n1", "c3", "3"):
                    target_line.n1 = numeric
    else:
        table = finance.tables.get(table_id)
        if not table:
            raise HTTPException(status_code=404, detail=f"Tabla '{table_id}' no encontrada")

        for cell_update in cells:
            row_idx = cell_update.get("row")
            col_id = cell_update.get("col")
            numeric = cell_update.get("numeric")
            value = cell_update.get("value", "")

            if row_idx is None or col_id is None:
                continue
            if not isinstance(row_idx, int) or row_idx < 0 or row_idx >= len(table.rows):
                continue

            existing = table.get_cell(row_idx, str(col_id))
            if existing is None:
                continue

            existing.numeric = numeric
            if numeric is not None:
                existing.value = _format_spanish(numeric)
            elif value:
                existing.value = value

    save_finance(project_id, finance)
    validation = validate_all(finance)
    return JSONResponse({
        "ok": True,
        "table_id": table_id,
        "validation": validation.model_dump(),
    })


@app.get("/projects/{project_id}/concept-impact")
async def get_concept_impact(
    project_id: str,
    label: str = "",
) -> JSONResponse:
    """Find other places where this concept or amount appears across financial statements."""
    try:
        finance = load_finance(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado") from exc
    impacts = find_concept_impact(finance, label)
    return JSONResponse({"label": label, "impacts": impacts})


@app.get("/projects/{project_id}/validate-cross")
async def validate_cross(project_id: str) -> JSONResponse:
    """Return full cross-validation results."""
    try:
        finance = load_finance(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado") from exc
    validation = validate_all(finance)
    return JSONResponse(validation.model_dump())


# ── Preview & PDF ──────────────────────────────────────────────────────────────

@app.get("/projects/{project_id}/preview", response_class=HTMLResponse)
async def preview_report(project_id: str) -> HTMLResponse:
    try:
        project = load_project(project_id)
        finance = load_finance(project_id)
        content = load_content(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado") from exc
    html = render_report_html(project, finance, content, editable=True)
    return HTMLResponse(html)


@app.get("/projects/{project_id}/pdf")
async def download_pdf(project_id: str) -> Response:
    try:
        project = load_project(project_id)
        finance = load_finance(project_id)
        content = load_content(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado") from exc

    html = render_report_html(project, finance, content, editable=False)
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


# ── Excel export ───────────────────────────────────────────────────────────────

@app.get("/projects/{project_id}/excel")
async def download_excel(project_id: str) -> FileResponse:
    """Export all financial data as a professional Excel workbook."""
    try:
        project = load_project(project_id)
        finance = load_finance(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado") from exc

    from app.services.excel_export import export_excel

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUTS_DIR / f"{project_id}_informe.xlsx"
    export_excel(project, finance, out)
    return FileResponse(
        path=out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{project.entity.legal_name} - Informe Financiero.xlsx",
    )


# ── DOCX import / create / rollover ────────────────────────────────────────────

def _slug_project_id(name: str) -> str:
    import re

    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "informe"
    candidate = base
    n = 2
    while project_dir(candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _parse_iso_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


@app.post("/projects/from-docx")
async def create_project_from_docx(
    file: UploadFile = File(...),
    current_end: Annotated[str, Form()] = "",
    apply_rollover: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Crear un informe nuevo partiendo de un DOCX del año anterior."""
    if not file.filename or not file.filename.lower().endswith(".docx"):
        return _flash_redirect("/", "Sube un archivo .docx", "error")

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUTS_DIR / f"_upload_new_{uuid4().hex[:8]}.docx"
    tmp.write_bytes(await file.read())
    try:
        from app.services.docx_importer import import_docx

        result = import_docx(tmp)
        legal_name = result.legal_name or "Nueva Sociedad"
        project_id = _slug_project_id(legal_name)

        detected = result.detected_current_end or date(date.today().year - 1, 12, 31)
        user_end = _parse_iso_date(current_end)
        try:
            detected_prior = detected.replace(year=detected.year - 1)
        except ValueError:
            detected_prior = detected.replace(year=detected.year - 1, day=28)

        project = Project(
            id=project_id,
            entity=Entity(
                legal_name=legal_name,
                legal_form_note=result.legal_form_note or "",
            ),
            period=Period(current_end=detected, prior_end=detected_prior),
            title=result.title,
        )
        finance = FinanceModel(tables=result.tables, facts=dict(result.facts))
        if result.balance_lines:
            finance.statements.balance = BalanceStatement(lines=result.balance_lines)
        if result.pyg_lines:
            finance.statements.pyg = PygStatement(lines=result.pyg_lines)
        content = result.content

        if apply_rollover in {"1", "on", "true", "yes"}:
            # DOCX = ejercicio cerrado → semilla del siguiente
            project, finance = rollover(
                project,
                finance,
                new_current_end=user_end,
                clear_current=True,
            )
        elif user_end is not None:
            try:
                prior = user_end.replace(year=user_end.year - 1)
            except ValueError:
                prior = user_end.replace(year=user_end.year - 1, day=28)
            project.period.current_end = user_end
            project.period.prior_end = prior

        save_project(project)
        save_finance(project_id, finance)
        save_content(project_id, content)
    except Exception as exc:
        return _flash_redirect("/", f"Error al crear desde DOCX: {exc}", "error")
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)

    return _flash_redirect(
        f"/projects/{project_id}?tab=preview",
        f"Informe creado desde DOCX: {len(content.blocks)} bloques, {len(finance.tables)} tablas, "
        f"{len(finance.statements.balance.lines)} líneas de Balance, "
        f"{len(finance.statements.pyg.lines)} de PyG.",
    )


@app.post("/projects/{project_id}/import-docx")
async def import_docx_endpoint(
    project_id: str,
    file: UploadFile = File(...),
) -> RedirectResponse:
    """Import structure from a DOCX file into an existing project."""
    if not file.filename or not file.filename.lower().endswith(".docx"):
        return _flash_redirect(
            f"/projects/{project_id}?tab=excel",
            "Sube un archivo .docx",
            "error",
        )
    tmp = OUTPUTS_DIR / f"_upload_{project_id}.docx"
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(await file.read())
    try:
        from app.services.docx_importer import import_docx

        result = import_docx(tmp)
        project = load_project(project_id)
        if result.legal_name:
            project.entity.legal_name = result.legal_name
        if result.legal_form_note:
            project.entity.legal_form_note = result.legal_form_note
        if result.detected_current_end:
            end = result.detected_current_end
            try:
                prior = end.replace(year=end.year - 1)
            except ValueError:
                prior = end.replace(year=end.year - 1, day=28)
            project.period.current_end = end
            project.period.prior_end = prior
        save_project(project)

        finance = load_finance(project_id)
        finance.tables = result.tables
        if result.balance_lines:
            finance.statements.balance = BalanceStatement(lines=result.balance_lines)
        if result.pyg_lines:
            finance.statements.pyg = PygStatement(lines=result.pyg_lines)
        if result.facts:
            finance.facts.update(result.facts)
        save_content(project_id, result.content)
        save_finance(project_id, finance)
        content = result.content
        tables = result.tables
        n_balance = len(result.balance_lines)
        n_pyg = len(result.pyg_lines)
    except Exception as exc:
        return _flash_redirect(
            f"/projects/{project_id}?tab=excel",
            f"Error al importar DOCX: {exc}",
            "error",
        )
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return _flash_redirect(
        f"/projects/{project_id}?tab=preview",
        f"DOCX importado: {len(content.blocks)} bloques, {len(tables)} tablas, "
        f"{n_balance} líneas de Balance, {n_pyg} de PyG.",
    )


@app.post("/projects/{project_id}/rollover")
async def rollover_endpoint(
    project_id: str,
    new_current_end: Annotated[str, Form()] = "",
    clear_current: Annotated[str, Form()] = "1",
) -> RedirectResponse:
    """Preparar el informe para el ejercicio siguiente (N → N-1)."""
    try:
        project = load_project(project_id)
        finance = load_finance(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado") from exc

    new_end = _parse_iso_date(new_current_end)
    project, finance = rollover(
        project,
        finance,
        new_current_end=new_end,
        clear_current=clear_current in {"1", "on", "true", "yes", ""},
    )
    save_project(project)
    save_finance(project_id, finance)
    return _flash_redirect(
        f"/projects/{project_id}?tab=datos",
        (
            f"Rollover aplicado. Nuevo ejercicio: {project.period.current_end} "
            f"(comparativo {project.period.prior_end}). "
            "Revisa y completa las cifras del año N."
        ),
    )


# ── Layout cases ───────────────────────────────────────────────────────────────

@app.post("/projects/{project_id}/layout-cases/{case_id}")
async def run_layout_case(project_id: str, case_id: str) -> RedirectResponse:
    try:
        content = load_content_seed(project_id)
        finance = load_finance_seed(project_id)
        content, finance = apply_case(case_id, content, finance)
        save_content(project_id, content)
        save_finance(project_id, finance)
    except ValueError as exc:
        return _flash_redirect(
            f"/projects/{project_id}?tab=layout",
            str(exc),
            "error",
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado") from exc
    title = next((c["title"] for c in CASES if c["id"] == case_id), case_id)
    return _flash_redirect(
        f"/projects/{project_id}?tab=preview",
        f"Caso {case_id} aplicado: {title}. Revisa el reflow en la vista previa.",
    )


@app.post("/projects/{project_id}/layout-cases/reset")
async def reset_layout_seed(project_id: str) -> RedirectResponse:
    try:
        save_content(project_id, load_content_seed(project_id))
        save_finance(project_id, load_finance_seed(project_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado") from exc
    return _flash_redirect(
        f"/projects/{project_id}?tab=layout",
        "Datos restaurados al seed de layout.",
    )


# ── Excel import (balance) ─────────────────────────────────────────────────────

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


# ── Helpers ────────────────────────────────────────────────────────────────────

def _format_spanish(value: float) -> str:
    """Format a number in Spanish locale (dot thousands, comma decimal)."""
    formatted = f"{abs(value):,.2f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    if value < 0:
        return f"({formatted})"
    return formatted
