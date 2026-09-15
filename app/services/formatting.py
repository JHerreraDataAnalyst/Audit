from __future__ import annotations

from datetime import date

_MONTHS_ES = [
    "",
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


def format_amount(value: float | None, zero_as_dash: bool = True) -> str:
    if value is None:
        return ""
    if zero_as_dash and abs(value) < 0.005:
        return "-"
    formatted = f"{value:,.2f}"
    # 1,234,567.89 -> 1.234.567,89
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def format_date_long(d: date) -> str:
    return f"{d.day} de {_MONTHS_ES[d.month]} de {d.year}"


def format_date_short(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def format_note_refs(refs: list[str]) -> str:
    if not refs:
        return ""
    if len(refs) == 1:
        return refs[0]
    if len(refs) == 2:
        return f"{refs[0]} y {refs[1]}"
    return f"{', '.join(refs[:-1])} y {refs[-1]}"
