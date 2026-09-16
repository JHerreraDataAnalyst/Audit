from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


LineRole = Literal["detail", "subtotal_group", "subtotal", "total", "header", "spacer"]


class BalanceLine(BaseModel):
    id: str
    label: str
    level: int = 1
    parent: str | None = None
    note_refs: list[str] = Field(default_factory=list)
    n: float = 0.0
    n1: float = 0.0
    role: LineRole = "detail"
    section: Literal["asset", "equity_liability"] = "asset"


class BalanceStatement(BaseModel):
    lines: list[BalanceLine] = Field(default_factory=list)


class PygLine(BaseModel):
    """Line of the Profit & Loss (Cuenta de pérdidas y ganancias)."""
    id: str
    label: str
    level: int = 1
    parent: str | None = None
    note_refs: list[str] = Field(default_factory=list)
    n: float = 0.0
    n1: float = 0.0
    role: LineRole = "detail"


class PygStatement(BaseModel):
    lines: list[PygLine] = Field(default_factory=list)


class Statements(BaseModel):
    balance: BalanceStatement = Field(default_factory=BalanceStatement)
    pyg: PygStatement = Field(default_factory=PygStatement)


# ── Generic financial table model ──────────────────────────────────────────────

class TableCell(BaseModel):
    """A single cell in a generic financial table."""
    value: str = ""
    numeric: float | None = None  # Parsed numeric value (None if non-numeric)
    bold: bool = False
    is_total: bool = False


class TableColumn(BaseModel):
    """Column definition for a generic table."""
    id: str
    header: str
    align: Literal["left", "center", "right"] = "right"
    is_amount: bool = False  # True → numeric formatting in display


class FinanceTable(BaseModel):
    """
    A generic editable financial table.

    Used for PyG, movimientos de intangibles, desglose de partidas, etc.
    Each row is a dict mapping column-id → TableCell.
    """
    id: str
    title: str
    columns: list[TableColumn] = Field(default_factory=list)
    rows: list[dict[str, TableCell]] = Field(default_factory=list)
    section: str = ""  # Logical section: "nota_5", "nota_6", etc.
    note_ref: str = ""  # Display reference: "5", "6 y 7"
    total_row_indices: list[int] = Field(default_factory=list)  # Rows that are totals

    def column_ids(self) -> list[str]:
        return [c.id for c in self.columns]

    def amount_column_ids(self) -> list[str]:
        return [c.id for c in self.columns if c.is_amount]

    def get_cell(self, row_idx: int, col_id: str) -> TableCell | None:
        if 0 <= row_idx < len(self.rows):
            return self.rows[row_idx].get(col_id)
        return None

    def set_cell(self, row_idx: int, col_id: str, cell: TableCell) -> None:
        if 0 <= row_idx < len(self.rows):
            self.rows[row_idx][col_id] = cell


# ── Main finance model ─────────────────────────────────────────────────────────

class FinanceModel(BaseModel):
    statements: Statements = Field(default_factory=Statements)
    facts: dict[str, float] = Field(default_factory=dict)
    tables: dict[str, FinanceTable] = Field(default_factory=dict)  # Generic tables

    def lines_by_section(self, section: str) -> list[BalanceLine]:
        return [ln for ln in self.statements.balance.lines if ln.section == section]

    def sum_role(self, section: str, role: str) -> float:
        return sum(
            ln.n
            for ln in self.statements.balance.lines
            if ln.section == section and ln.role == role
        )

    def total_assets_n(self) -> float:
        totals = [
            ln.n
            for ln in self.statements.balance.lines
            if ln.section == "asset" and ln.role == "total"
        ]
        if totals:
            return totals[-1]
        return sum(
            ln.n
            for ln in self.statements.balance.lines
            if ln.section == "asset" and ln.role == "detail"
        )

    def total_equity_liability_n(self) -> float:
        totals = [
            ln.n
            for ln in self.statements.balance.lines
            if ln.section == "equity_liability" and ln.role == "total"
        ]
        if totals:
            return totals[-1]
        return sum(
            ln.n
            for ln in self.statements.balance.lines
            if ln.section == "equity_liability" and ln.role == "detail"
        )
