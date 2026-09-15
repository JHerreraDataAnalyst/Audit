from __future__ import annotations

import re
from typing import Any

from app.domain.content import ContentModel
from app.domain.finance import FinanceModel
from app.domain.project import Project
from app.domain.validation import ValidationResult, validate_balance
from app.services.formatting import (
    format_amount,
    format_date_long,
    format_date_short,
    format_note_refs,
)

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def build_context(project: Project, finance: FinanceModel, content: ContentModel) -> dict[str, Any]:
    validation = validate_balance(finance)
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

    resolved_blocks = []
    for block in content.blocks:
        resolved_blocks.append(
            {
                "id": block.id,
                "kind": block.kind,
                "text": _resolve_text(block.text, placeholders),
                "raw": block.text,
            }
        )

    blocks_by_id = {b["id"]: b for b in resolved_blocks}

    asset_lines = []
    equity_lines = []
    for line in finance.statements.balance.lines:
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

    return {
        "project": project,
        "entity": project.entity,
        "period": period_ctx,
        "blocks": resolved_blocks,
        "block": blocks_by_id,
        "asset_lines": asset_lines,
        "equity_lines": equity_lines,
        "facts": finance.facts,
        "validation": validation,
        "totals": {
            "assets_n": finance.total_assets_n(),
            "equity_liability_n": finance.total_equity_liability_n(),
            "assets_n_fmt": format_amount(finance.total_assets_n(), zero_as_dash=False),
            "equity_liability_n_fmt": format_amount(
                finance.total_equity_liability_n(), zero_as_dash=False
            ),
        },
    }


def _resolve_text(text: str, placeholders: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return placeholders.get(key, match.group(0))

    return _PLACEHOLDER.sub(repl, text)


def get_validation(finance: FinanceModel) -> ValidationResult:
    return validate_balance(finance)
