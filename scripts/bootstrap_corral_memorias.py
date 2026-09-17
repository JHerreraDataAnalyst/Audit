"""
Bootstrap Corral small-entity report projects in the local program.

Uses MEMORIA IC.docx as structural note/reference seed (Luis),
rollover/blanqueo to ejercicio 2025, then overlays Balance/PyG 2025
from BALANCES GRUPO V5 / Balance {ENT} Excel. Comparativo N-1 starts at 0
until CCAA 2024 figures are mapped per entity.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import openpyxl
from docx import Document  # type: ignore[import-untyped]

from app.domain.content import ContentBlock, ContentModel
from app.domain.finance import (
    BalanceLine,
    BalanceStatement,
    FinanceModel,
    PygLine,
    PygStatement,
    is_publishable_statement_line,
)
from app.domain.project import Entity, Period, Project
from app.services.docx_importer import import_docx
from app.services.rollover import rollover
from app.services.storage import save_content, save_finance, save_project

CLIENT = ROOT / "clientes" / "INMOBILIARIA CORRAL, S.L"
MEMORIA_IC = CLIENT / "MEMORIA IC.docx"
V5 = (
    CLIENT
    / "2. Conso Inmobiliaria Corral, SA"
    / "ULTIMOS BALANCES"
    / "BALANCES GRUPO V5.xlsx"
)
BAL_DIR = (
    CLIENT
    / "2. Conso Inmobiliaria Corral, SA"
    / "Proceso consolidación"
    / "Info para consolidado"
    / "Balances"
)

ENTITIES = {
    "pgf": {
        "legal_name": "PROMOCIONES GRAN FERIAL DE COSLADA, S.L.U.",
        "legal_form_note": "Sociedad Unipersonal",
        "project_id": "pgf-promociones-gran-ferial",
        "v5_company": "PROM. GRAN FERIAL COSLADA",
        "balance_xlsx": "Balance PGF - Promociones Gran Ferial 2025.xlsx",
        "balance_sheet": "PGF",
    },
    "pbp": {
        "legal_name": "PROMOCIONES BARRIO DEL PUERTO DE COSLADA, S.L.",
        "legal_form_note": "",
        "project_id": "pbp-promociones-barrio-puerto",
        "v5_company": "PROM BARRIO DEL PUERTO COSLA",
        "balance_xlsx": "Balance PBP - Promociones Barrio del Puerto 2025.xlsx",
        "balance_sheet": "PBP",
    },
    "cca": {
        "legal_name": "COSLADA COCHES DE ALQUILER, S.L.U.",
        "legal_form_note": "Sociedad Unipersonal",
        "project_id": "cca-coslada-coches-alquiler",
        "v5_company": "COSLADA COCHES DE ALQUILER",
        "balance_xlsx": "Balance CCA - Coslada Coches de Alquiler 2025.xlsx",
        "balance_sheet": "CCA",
    },
    "autotype": {
        "legal_name": "AUTOTYPE, S.L.",
        "legal_form_note": "",
        "project_id": "autotype-sl",
        "v5_company": "AUTOTYPE",
        "balance_xlsx": "Balance AUT - Autotype 2025.xlsx",
        "balance_sheet": "AUT",
    },
}


def _slug(label: str) -> str:
    s = label.lower()
    s = (
        s.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return (s[:60] or "linea")


def _role_and_level(label: str) -> tuple[str, int]:
    t = label.strip()
    if re.match(r"^TOTAL\b", t, re.I):
        return "total", 1
    if re.match(r"^[A-Z]\)\s", t) or re.match(r"^[A-Z]-\d", t):
        return "subtotal_group", 1
    if re.match(r"^[IVXLC]+\.\s", t):
        return "subtotal_group", 2
    if re.match(r"^\d+\.\s", t) or re.match(r"^[a-z]\)\s", t):
        return "detail", 3
    return "detail", 2


def _find_company_cols(ws, company_needle: str) -> tuple[int, int]:
    """Return (col_2025, col_2026) 1-based for company header in BALANCES GRUPO."""
    needle = company_needle.upper()
    for col in range(1, ws.max_column + 1):
        val = ws.cell(3, col).value
        if val and needle in str(val).upper():
            # amount cols are usually col and col+1 under this header block
            # Header sits on the first amount column of the block (see row 6)
            y1 = ws.cell(6, col).value
            y2 = ws.cell(6, col + 1).value
            if y1 in (2025, "2025"):
                return col, col + 1
            # sometimes company name is on col, years on col / col+1
            for c in range(col, col + 3):
                if ws.cell(6, c).value in (2025, "2025"):
                    return c, c + 1
    raise KeyError(f"Company not found in V5: {company_needle}")


def balance_from_v5(company_needle: str) -> list[BalanceLine]:
    wb = openpyxl.load_workbook(V5, data_only=True)
    ws = wb["BALANCES GRUPO"]
    col_n, _col_n1 = _find_company_cols(ws, company_needle)

    lines: list[BalanceLine] = []
    section: str = "asset"
    seen: set[str] = set()
    for row in range(7, ws.max_row + 1):
        label = ws.cell(row, 1).value
        if label is None or str(label).strip() == "":
            continue
        label_s = re.sub(r"\s+", " ", str(label)).strip()
        upper = label_s.upper()
        if not is_publishable_statement_line(label=label_s):
            continue
        if "PATRIMONIO NETO" in upper or upper.startswith("B) PASIVO") or "PASIVO" == upper:
            section = "equity_liability"
        if upper in {"ACTIVO", "PASIVO"} or upper.startswith("BALANCE"):
            continue

        amount = ws.cell(row, col_n).value
        try:
            n = float(amount or 0)
        except (TypeError, ValueError):
            n = 0.0

        role, level = _role_and_level(label_s)
        base_id = _slug(label_s)
        lid = base_id
        i = 2
        while lid in seen:
            lid = f"{base_id}_{i}"
            i += 1
        seen.add(lid)

        lines.append(
            BalanceLine(
                id=lid,
                label=label_s,
                level=level,
                section=section,  # type: ignore[arg-type]
                role=role,  # type: ignore[arg-type]
                n=round(n, 2),
                n1=0.0,
            )
        )
    return lines


def pyg_from_entity_excel(cfg: dict) -> list[PygLine]:
    path = BAL_DIR / cfg["balance_xlsx"]
    if not path.exists():
        return []
    wb = openpyxl.load_workbook(path, data_only=True)
    sheet = cfg["balance_sheet"]
    if sheet not in wb.sheetnames:
        sheet = wb.sheetnames[0]
    ws = wb[sheet]

    # Find PyG start: first row with "pérdidas" / "RESULTADO DE EXPLOT" / "1. Importe neto"
    start = None
    for r in range(1, ws.max_row + 1):
        b = ws.cell(r, 2).value
        if not b:
            continue
        t = str(b).upper()
        if "IMPORTE NETO DE LA CIFRA" in t or "CUENTA DE P" in t:
            start = r
            break
        if t.startswith("1. IMPORTE NETO"):
            start = r
            break
    if start is None:
        # fallback: after TOTAL PASIVO area ~ row 130+
        start = 130

    lines: list[PygLine] = []
    seen: set[str] = set()
    for r in range(start, ws.max_row + 1):
        label = ws.cell(r, 2).value
        if label is None or str(label).strip() == "":
            continue
        label_s = re.sub(r"\s+", " ", str(label)).strip()
        if not is_publishable_statement_line(label=label_s):
            continue
        raw = ws.cell(r, 3).value  # PREVIO
        try:
            n = float(raw or 0)
        except (TypeError, ValueError):
            n = 0.0
        role, level = _role_and_level(label_s)
        if "RESULTADO" in label_s.upper() and label_s.upper().startswith("A"):
            role = "total" if "A.5" in label_s.upper() or "A)" == label_s.upper()[:2] else "subtotal"
        base_id = _slug(label_s)
        lid = base_id
        i = 2
        while lid in seen:
            lid = f"{base_id}_{i}"
            i += 1
        seen.add(lid)
        lines.append(
            PygLine(
                id=lid,
                label=label_s,
                level=level,
                role=role,  # type: ignore[arg-type]
                n=round(n, 2),
                n1=0.0,
            )
        )
    return lines


def adapt_content_for_entity(content: ContentModel, legal_name: str) -> ContentModel:
    """Keep note structure; stamp entity name on cover-like blocks."""
    blocks: list[ContentBlock] = []
    for b in content.blocks:
        nb = b.model_copy(deep=True)
        if nb.kind in {"title", "heading1"} and "INMOBILIARIA CORRAL" in nb.text.upper():
            nb.text = legal_name
        blocks.append(nb)
    # Ensure a visible working note at top of memoria
    banner = ContentBlock(
        id="p.bootstrap_corral_banner",
        kind="paragraph",
        text=(
            f"Borrador de trabajo {legal_name} — ejercicio 2025. "
            "Estructura de notas tomada como referencia de MEMORIA IC; "
            "cifras N cargadas desde balances 2025; comparativo N-1 pendiente "
            "de mapear desde CCAA 2024 de la sociedad."
        ),
        section="nota_1",
        visible=True,
    )
    # insert after first heading1 if possible
    out: list[ContentBlock] = []
    inserted = False
    for b in blocks:
        out.append(b)
        if not inserted and b.kind == "heading1":
            out.append(banner)
            inserted = True
    if not inserted:
        out.insert(0, banner)
    return ContentModel(blocks=out)


def bootstrap_entity(key: str) -> str:
    cfg = ENTITIES[key]
    print(f"=== {key}: {cfg['legal_name']} ===")
    assert MEMORIA_IC.exists(), MEMORIA_IC
    assert V5.exists(), V5

    result = import_docx(MEMORIA_IC)
    project = Project(
        id=cfg["project_id"],
        entity=Entity(
            legal_name=cfg["legal_name"],
            legal_form_note=cfg["legal_form_note"],
        ),
        period=Period(
            current_end=date(2024, 12, 31),
            prior_end=date(2023, 12, 31),
        ),
        title="Cuentas Anuales",
    )
    finance = FinanceModel(tables=result.tables, facts=dict(result.facts))
    if result.balance_lines:
        finance.statements.balance = BalanceStatement(lines=result.balance_lines)
    if result.pyg_lines:
        finance.statements.pyg = PygStatement(lines=result.pyg_lines)

    # Blanqueo → ejercicio 2025
    project, finance = rollover(
        project,
        finance,
        new_current_end=date(2025, 12, 31),
        clear_current=True,
    )

    # Overlay entity balances 2025 (N); keep N-1 at 0 (true blank for this entity)
    bal_lines = balance_from_v5(cfg["v5_company"])
    finance.statements.balance = BalanceStatement(lines=bal_lines)
    pyg_lines = pyg_from_entity_excel(cfg)
    if pyg_lines:
        finance.statements.pyg = PygStatement(lines=pyg_lines)

    content = adapt_content_for_entity(result.content, cfg["legal_name"])

    save_project(project)
    save_finance(project.id, finance)
    save_content(project.id, content)

    tot_a = finance.total_assets_n()
    tot_p = finance.total_equity_liability_n()
    print(
        f"  saved data/projects/{project.id}/ | "
        f"balance lines={len(bal_lines)} assets={tot_a:,.2f} pn+pas={tot_p:,.2f} "
        f"diff={tot_a - tot_p:,.2f} | pyg={len(finance.statements.pyg.lines)} | "
        f"blocks={len(content.blocks)} tables={len(finance.tables)}"
    )
    return project.id


def main(argv: list[str]) -> None:
    keys = argv[1:] or ["pgf"]
    if keys == ["all"]:
        keys = list(ENTITIES)
    for k in keys:
        if k not in ENTITIES:
            raise SystemExit(f"Unknown entity {k}. Choose: {', '.join(ENTITIES)}")
        bootstrap_entity(k)


if __name__ == "__main__":
    main(sys.argv)
