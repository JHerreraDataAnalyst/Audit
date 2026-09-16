"""
Rollover de ejercicio: convierte un informe cerrado en la semilla del siguiente.

- Fechas: prior_end ← current_end; current_end ← +1 año (o fecha indicada)
- Balance tipado: N-1 ← N; N ← 0 (opcional)
- Tablas genéricas: desplaza columnas de importes N → N-1
- Facts: claves *_N → *_N1 cuando aplica
"""

from __future__ import annotations

from datetime import date

from app.domain.finance import FinanceModel, FinanceTable, TableCell
from app.domain.project import Period, Project


def _add_one_year(d: date) -> date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        # 29-feb → 28-feb del año siguiente
        return d.replace(year=d.year + 1, day=28)


def _format_spanish(value: float | None) -> str:
    if value is None:
        return ""
    formatted = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if value < 0:
        return f"({formatted})"
    return formatted


def rollover_project(project: Project, new_current_end: date | None = None) -> Project:
    """Advance project period for a new fiscal year."""
    updated = project.model_copy(deep=True)
    old_current = updated.period.current_end
    updated.period = Period(
        current_end=new_current_end or _add_one_year(old_current),
        prior_end=old_current,
        currency=updated.period.currency,
        currency_label=updated.period.currency_label,
    )
    return updated


def _rollover_table(table: FinanceTable, clear_current: bool) -> FinanceTable:
    """
    For tables with amount columns, shift values toward comparative (N-1).

    Heuristic: first two amount columns are (N, N-1).
    """
    amount_cols = [c.id for c in table.columns if c.is_amount]
    if len(amount_cols) < 2:
        return table

    current_id, prior_id = amount_cols[0], amount_cols[1]
    new_rows: list[dict[str, TableCell]] = []
    for row in table.rows:
        new_row = {k: v.model_copy(deep=True) for k, v in row.items()}
        cur = new_row.get(current_id)
        prior = new_row.get(prior_id)
        if cur is not None and prior is not None:
            prior.numeric = cur.numeric
            prior.value = cur.value if cur.value else _format_spanish(cur.numeric)
            prior.bold = cur.bold
            prior.is_total = cur.is_total
            if clear_current:
                if cur.numeric is not None or cur.value:
                    cur.numeric = 0.0
                    cur.value = _format_spanish(0.0)
        new_rows.append(new_row)

    out = table.model_copy(deep=True)
    out.rows = new_rows
    return out


def rollover_finance(finance: FinanceModel, clear_current: bool = True) -> FinanceModel:
    """Shift comparative columns for balance, facts and generic tables."""
    updated = finance.model_copy(deep=True)

    for line in updated.statements.balance.lines:
        line.n1 = line.n
        if clear_current:
            line.n = 0.0

    for line in updated.statements.pyg.lines:
        line.n1 = line.n
        if clear_current:
            line.n = 0.0

    new_facts: dict[str, float] = dict(updated.facts)
    for key, value in list(updated.facts.items()):
        upper = key.upper()
        if upper.endswith("_N") and not upper.endswith("_N1"):
            n1_key = f"{key[:-2]}_N1"
            new_facts[n1_key] = value
            if clear_current:
                new_facts[key] = 0.0
    updated.facts = new_facts

    updated.tables = {
        tid: _rollover_table(tbl, clear_current=clear_current)
        for tid, tbl in updated.tables.items()
    }
    return updated


def rollover(
    project: Project,
    finance: FinanceModel,
    *,
    new_current_end: date | None = None,
    clear_current: bool = True,
) -> tuple[Project, FinanceModel]:
    """Full rollover: period + financial figures."""
    return (
        rollover_project(project, new_current_end=new_current_end),
        rollover_finance(finance, clear_current=clear_current),
    )
