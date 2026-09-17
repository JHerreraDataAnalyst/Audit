from __future__ import annotations

import re
from typing import Any

from app.domain.content import ContentModel
from app.domain.finance import FinanceModel, FinanceTable
from app.domain.project import Project
from app.domain.validation import ValidationResult, validate_balance, validate_all
from app.services.formatting import (
    format_amount,
    format_date_long,
    format_date_short,
    format_note_refs,
)

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def build_context(project: Project, finance: FinanceModel, content: ContentModel) -> dict[str, Any]:
    validation = validate_all(finance)
    period_ctx = {
        "current_end": project.period.current_end,
        "prior_end": project.period.prior_end,
        "current_end_long": format_date_long(project.period.current_end),
        "prior_end_long": format_date_long(project.period.prior_end),
        "current_end_short": format_date_short(project.period.current_end),
        "prior_end_short": format_date_short(project.period.prior_end),
        "currency_label": project.period.currency_label,
        "current_year": project.period.current_end.year,
        "prior_year": project.period.prior_end.year,
    }

    placeholders = {
        "period.current_end_long": period_ctx["current_end_long"],
        "period.prior_end_long": period_ctx["prior_end_long"],
        "period.current_end_short": period_ctx["current_end_short"],
        "period.prior_end_short": period_ctx["prior_end_short"],
        "period.current_year": str(period_ctx["current_year"]),
        "period.prior_year": str(period_ctx["prior_year"]),
        "entity.legal_name": project.entity.legal_name,
    }
    for key, value in finance.facts.items():
        placeholders[f"fact.{key}"] = format_amount(value, zero_as_dash=False)

    cover_ids = {"cover.subtitle", "cover.management", "balance.caption"}
    resolved_blocks = []
    for block in content.visible_blocks():
        resolved_blocks.append(
            {
                "id": block.id,
                "kind": block.kind,
                "text": _resolve_text(block.text, placeholders),
                "raw": block.text,
                "section": block.section,
                "note_number": block.note_number,
                "table_id": block.table_id,
                "keep_with_next": block.keep_with_next,
                "highlight": block.highlight,
            }
        )

    blocks_by_id = {b["id"]: b for b in resolved_blocks}
    narrative = [
        b
        for b in resolved_blocks
        if b["kind"] == "paragraph" and b["id"] not in cover_ids
    ]

    asset_lines = []
    equity_lines = []
    for line in finance.statements.balance.lines:
        if not line.is_publishable():
            continue
        row = {
            "id": line.id,
            "label": line.label,
            "level": line.level,
            "role": line.role,
            "section": line.section,
            "note": format_note_refs(line.note_refs),
            "n": line.n,
            "n1": line.n1,
            "n_fmt": format_amount(line.n),
            "n1_fmt": format_amount(line.n1),
            "is_total": line.role in ("total", "subtotal"),
            "is_group": line.role == "subtotal_group",
        }
        if line.section == "asset":
            asset_lines.append(row)
        else:
            equity_lines.append(row)

    pyg_lines = []
    for line in finance.statements.pyg.lines:
        if not line.is_publishable():
            continue
        pyg_lines.append(
            {
                "id": line.id,
                "label": line.label,
                "level": line.level,
                "role": line.role,
                "note": format_note_refs(line.note_refs),
                "n": line.n,
                "n1": line.n1,
                "n_fmt": format_amount(line.n),
                "n1_fmt": format_amount(line.n1),
                "is_total": line.role in ("total", "subtotal"),
                "is_group": line.role == "subtotal_group",
                "is_header": line.role == "header",
            }
        )

    # Build generic tables context
    tables_ctx: dict[str, dict[str, Any]] = {}
    for table_id, table in finance.tables.items():
        tables_ctx[table_id] = _build_table_context(table)

    return {
        "project": project,
        "entity": project.entity,
        "period": period_ctx,
        "blocks": resolved_blocks,
        "block": blocks_by_id,
        "narrative": narrative,
        "asset_lines": asset_lines,
        "equity_lines": equity_lines,
        "pyg_lines": pyg_lines,
        "facts": finance.facts,
        "validation": validation,
        "tables": tables_ctx,
        "tables_list": [
            {"id": tid, "title": t.title, "section": t.section, "rows": len(t.rows), "cols": len(t.columns)}
            for tid, t in finance.tables.items()
        ],
        "totals": {
            "assets_n": finance.total_assets_n(),
            "equity_liability_n": finance.total_equity_liability_n(),
            "assets_n_fmt": format_amount(finance.total_assets_n(), zero_as_dash=False),
            "equity_liability_n_fmt": format_amount(
                finance.total_equity_liability_n(), zero_as_dash=False
            ),
        },
    }


def _build_table_context(table: FinanceTable) -> dict[str, Any]:
    """Convert a FinanceTable to a template-friendly dict."""
    cols = []
    for i, c in enumerate(table.columns):
        kind = "label" if i == 0 else "amount" if c.is_amount else "note"
        header_l = (c.header or "").lower()
        if i > 0 and not c.is_amount:
            if any(k in header_l for k in ("direcci", "nombre", "actividad", "descrip")):
                kind = "text-wide" if "direcci" in header_l or "nombre" in header_l else "text"
            elif c.align == "left":
                kind = "text"
            elif header_l == "nota" or c.align == "center":
                kind = "note"
            else:
                kind = "text"
        cols.append(
            {
                "id": c.id,
                "header": c.header,
                "align": c.align,
                "is_amount": c.is_amount,
                "kind": kind,
            }
        )
    rows_ctx = []
    for row_idx, row in enumerate(table.rows):
        cells = []
        for col in table.columns:
            cell = row.get(col.id)
            if cell:
                display = cell.value
                if col.is_amount and cell.numeric is not None:
                    display = format_amount(cell.numeric, zero_as_dash=False)
                cells.append({
                    "value": display,
                    "numeric": cell.numeric,
                    "bold": cell.bold,
                    "is_total": cell.is_total,
                    "raw": cell.value,
                })
            else:
                cells.append({"value": "", "numeric": None, "bold": False, "is_total": False, "raw": ""})
        rows_ctx.append({
            "index": row_idx,
            "cells": cells,
            "is_total": row_idx in table.total_row_indices,
        })
    return {
        "id": table.id,
        "title": table.title,
        "columns": cols,
        "rows": rows_ctx,
        "section": table.section,
        "col_count": len(cols),
        "dense": len(cols) >= 5,
    }


def _resolve_text(text: str, placeholders: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return placeholders.get(key, match.group(0))

    return _PLACEHOLDER.sub(repl, text)


def get_validation(finance: FinanceModel) -> ValidationResult:
    return validate_all(finance)
