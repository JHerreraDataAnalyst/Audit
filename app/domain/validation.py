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


def _fmt(value: float) -> str:
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return formatted
