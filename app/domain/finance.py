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


class Statements(BaseModel):
    balance: BalanceStatement = Field(default_factory=BalanceStatement)


class FinanceModel(BaseModel):
    statements: Statements = Field(default_factory=Statements)
    facts: dict[str, float] = Field(default_factory=dict)

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
