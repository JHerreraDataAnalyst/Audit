from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.finance import FinanceModel


class ValidationIssue(BaseModel):
    code: str
    severity: str  # error | warning | ok
    message: str
    expected: float | None = None
    actual: float | None = None
    difference: float | None = None
    table_id: str | None = None  # Table where the issue was found


class ValidationResult(BaseModel):
    ok: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


def validate_balance(finance: FinanceModel, tolerance: float = 0.01) -> ValidationResult:
    assets = finance.total_assets_n()
    equity_liab = finance.total_equity_liability_n()
    diff = round(assets - equity_liab, 2)
    issues: list[ValidationIssue] = []

    if abs(diff) > tolerance:
        issues.append(
            ValidationIssue(
                code="BALANCE_NOT_BALANCED",
                severity="error",
                message=(
                    f"Balance no cuadrado: Activo ({_fmt(assets)}) ≠ "
                    f"Pasivo + Patrimonio neto ({_fmt(equity_liab)})."
                ),
                expected=assets,
                actual=equity_liab,
                difference=diff,
            )
        )
    else:
        issues.append(
            ValidationIssue(
                code="BALANCE_OK",
                severity="ok",
                message=f"Balance cuadrado. Activo = Pasivo + PN = {_fmt(assets)}.",
                expected=assets,
                actual=equity_liab,
                difference=0.0,
            )
        )

    # Soft check: detail lines should be present
    asset_details = [
        ln for ln in finance.statements.balance.lines if ln.section == "asset" and ln.role == "detail"
    ]
    if not asset_details:
        issues.append(
            ValidationIssue(
                code="NO_ASSET_DETAILS",
                severity="warning",
                message="No hay líneas de detalle en el Activo.",
            )
        )

    ok = not any(i.severity == "error" for i in issues)
    return ValidationResult(ok=ok, issues=issues)


def validate_table_totals(finance: FinanceModel, tolerance: float = 0.50) -> ValidationResult:
    """Verify that total rows in each table sum correctly from detail rows."""
    issues: list[ValidationIssue] = []

    for table_id, table in finance.tables.items():
        if not table.total_row_indices or not table.amount_column_ids():
            continue

        amount_cols = table.amount_column_ids()

        for total_idx in table.total_row_indices:
            if total_idx >= len(table.rows):
                continue

            total_row = table.rows[total_idx]

            for col_id in amount_cols:
                total_cell = total_row.get(col_id)
                if not total_cell or total_cell.numeric is None:
                    continue

                # Sum detail rows above this total (between previous total and this one)
                prev_total = -1
                for ti in table.total_row_indices:
                    if ti < total_idx:
                        prev_total = ti
                detail_sum = 0.0
                detail_count = 0
                for ri in range(prev_total + 1, total_idx):
                    cell = table.rows[ri].get(col_id)
                    if cell and cell.numeric is not None:
                        detail_sum += cell.numeric
                        detail_count += 1

                if detail_count == 0:
                    continue

                diff = round(abs(detail_sum - total_cell.numeric), 2)
                if diff > tolerance:
                    label_cell = total_row.get("c0")
                    label = label_cell.value if label_cell else f"Fila {total_idx}"
                    col_header = next(
                        (c.header for c in table.columns if c.id == col_id),
                        col_id,
                    )
                    issues.append(
                        ValidationIssue(
                            code="TABLE_TOTAL_MISMATCH",
                            severity="warning",
                            message=(
                                f"Tabla '{table.title[:40]}': el total '{label}' en columna "
                                f"'{col_header[:30]}' no cuadra. "
                                f"Suma detalle={_fmt(detail_sum)}, Total={_fmt(total_cell.numeric)}."
                            ),
                            expected=detail_sum,
                            actual=total_cell.numeric,
                            difference=diff,
                            table_id=table_id,
                        )
                    )

    if not issues:
        issues.append(
            ValidationIssue(
                code="TABLE_TOTALS_OK",
                severity="ok",
                message="Totales internos de tablas verificados.",
            )
        )

    ok = not any(i.severity == "error" for i in issues)
    return ValidationResult(ok=ok, issues=issues)


def validate_cross_references(finance: FinanceModel, tolerance: float = 0.50) -> ValidationResult:
    """
    Detect amounts that appear in multiple tables and check consistency.

    Builds a map of significant amounts → list of locations,
    then flags when the same concept appears with different values.
    """
    issues: list[ValidationIssue] = []

    amount_registry: dict[str, list[tuple[str, str, float]]] = {}

    # Register balance lines so cross-references check Balance vs Memoria tables
    for line in finance.statements.balance.lines:
        label = line.label.strip().lower()
        if not label or label == "total" or len(label) < 5:
            continue
        key = label[:50]
        if key not in amount_registry:
            amount_registry[key] = []
        if abs(line.n) > 0.01:
            amount_registry[key].append(("Balance", "N", line.n))
        if abs(line.n1) > 0.01:
            amount_registry[key].append(("Balance", "N-1", line.n1))

    # Register all generic tables
    for table_id, table in finance.tables.items():
        for row_idx, row in enumerate(table.rows):
            label_cell = row.get("c0")
            if not label_cell:
                continue
            label = label_cell.value.strip().lower()
            if not label or label == "total" or len(label) < 5:
                continue
            for col in table.columns:
                if not col.is_amount:
                    continue
                cell = row.get(col.id)
                if cell and cell.numeric is not None and abs(cell.numeric) > 0.01:
                    key = label[:50]
                    if key not in amount_registry:
                        amount_registry[key] = []
                    t_title = table.title[:25] if table.title else table_id
                    amount_registry[key].append((t_title, col.header, cell.numeric))

    # Find labels that appear in multiple tables with different values
    for label, occurrences in amount_registry.items():
        if len(occurrences) < 2:
            continue
        table_ids = set(t[0] for t in occurrences)
        if len(table_ids) < 2:
            continue  # Same table, skip

        # Compare values for the same period (e.g. N with N, or find if there is divergence)
        values = set(round(v, 2) for _, _, v in occurrences)
        if len(values) > 1:
            locations = ", ".join(
                f"{tid} ({col}: {_fmt(val)})"
                for tid, col, val in occurrences[:4]
            )
            issues.append(
                ValidationIssue(
                    code="CROSS_REF_MISMATCH",
                    severity="warning",
                    message=(
                        f"'{label[:40]}' tiene valores diferentes entre estados/tablas: {locations}"
                    ),
                )
            )

    if not issues:
        issues.append(
            ValidationIssue(
                code="CROSS_REF_OK",
                severity="ok",
                message="Referencias cruzadas entre Balance y tablas de Memoria verificadas.",
            )
        )

    ok = not any(i.severity == "error" for i in issues)
    return ValidationResult(ok=ok, issues=issues)


def find_concept_impact(finance: FinanceModel, label: str, current_value: float | None = None) -> list[dict]:
    """Find other places in the financial statements where this concept or amount appears."""
    matches = []
    clean_label = label.strip().lower()
    
    # Check Balance
    for line in finance.statements.balance.lines:
        line_clean = line.label.strip().lower()
        if clean_label and (clean_label in line_clean or line_clean in clean_label):
            matches.append({
                "source": "Balance de Situación",
                "table_id": "balance_asset" if line.section == "asset" else "balance_equity",
                "label": line.label,
                "n": line.n,
                "n_fmt": _fmt(line.n),
                "n1": line.n1,
                "n1_fmt": _fmt(line.n1),
            })
            
    # Check generic tables
    for tid, table in finance.tables.items():
        for row_idx, row in enumerate(table.rows):
            c0 = row.get("c0")
            if not c0 or not c0.value:
                continue
            r_label = c0.value.strip().lower()
            if clean_label and (clean_label in r_label or r_label in clean_label):
                amounts = {}
                for col in table.columns:
                    cell = row.get(col.id)
                    if cell and cell.numeric is not None:
                        amounts[col.header] = _fmt(cell.numeric)
                matches.append({
                    "source": table.title or f"Tabla {tid}",
                    "table_id": tid,
                    "row": row_idx,
                    "label": c0.value,
                    "amounts": amounts,
                })

    return matches


def validate_all(finance: FinanceModel) -> ValidationResult:
    """Run all validation rules."""
    all_issues: list[ValidationIssue] = []
    all_issues.extend(validate_balance(finance).issues)
    all_issues.extend(validate_table_totals(finance).issues)
    all_issues.extend(validate_cross_references(finance).issues)
    ok = not any(i.severity == "error" for i in all_issues)
    return ValidationResult(ok=ok, issues=all_issues)


def _fmt(value: float) -> str:
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return formatted

