"""
Extract typed BalanceLine rows from CCAA DOCX balance tables (Activo / Pasivo).

Hierarchy is inferred by matching parent amounts to the sum of following lines
(common PGC layout in Word). Totals are detected by label.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.finance import BalanceLine, is_publishable_statement_line


_NOTE_SPLIT = re.compile(r"\s*(?:,|;| y | Y )\s*")
_TOTAL_RE = re.compile(r"^\s*total\b", re.IGNORECASE)
_TOTAL_FINAL_ASSET = re.compile(r"^\s*total\s+activo\s*$", re.IGNORECASE)
_TOTAL_FINAL_EQUITY = re.compile(
    r"^\s*total\s+patrimonio\s+neto\s+y\s+pasivo\s*$", re.IGNORECASE
)


def _parse_spanish_number(text: str) -> float | None:
    clean = text.strip()
    if not clean or clean in {"-", "–", "—"}:
        return None
    negative = False
    if clean.startswith("(") and clean.endswith(")"):
        negative = True
        clean = clean[1:-1].strip()
    elif clean.startswith("-"):
        negative = True
        clean = clean[1:].strip()
    clean = clean.replace(".", "").replace(",", ".")
    try:
        val = float(clean)
        return -val if negative else val
    except ValueError:
        return None


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    for a, b in (
        ("áàä", "a"), ("éèë", "e"), ("íìï", "i"), ("óòö", "o"), ("úùü", "u"), ("ñ", "n"),
    ):
        for ch in a:
            slug = slug.replace(ch, b)
    slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")
    return slug[:50] if slug else "line"


@dataclass
class _RawBalanceRow:
    label: str
    note_refs: list[str]
    n: float
    n1: float
    bold: bool = False


def _parse_note_refs(text: str) -> list[str]:
    clean = text.strip()
    if not clean or clean in {"-", "–", "—"}:
        return []
    return [p.strip() for p in _NOTE_SPLIT.split(clean) if p.strip()]


def _cell_bold(cell: object) -> bool:
    try:
        for p in cell.paragraphs:  # type: ignore[attr-defined]
            for r in p.runs:
                if r.bold is True:
                    return True
    except Exception:
        pass
    return False


def _extract_amount_pair(cells: list[str]) -> tuple[float, float] | None:
    if len(cells) >= 7:
        raw_n, raw_n1 = cells[4].strip(), cells[6].strip()
        n = 0.0 if raw_n in {"-", "–", "—"} else _parse_spanish_number(raw_n)
        n1 = 0.0 if raw_n1 in {"-", "–", "—"} else _parse_spanish_number(raw_n1)
        if n is None and n1 is None:
            return None
        return (n or 0.0, n1 or 0.0)

    nums: list[float] = []
    for c in cells[1:]:
        v = _parse_spanish_number(c)
        if v is not None:
            nums.append(v)
        elif c.strip() in {"-", "–", "—"}:
            nums.append(0.0)
    if len(nums) >= 2:
        return nums[-2], nums[-1]
    if len(nums) == 1:
        return nums[0], 0.0
    return None


def parse_balance_table_rows(tbl: object) -> list[_RawBalanceRow]:
    rows_out: list[_RawBalanceRow] = []
    for row in tbl.rows:  # type: ignore[attr-defined]
        cells = [c.text.strip().replace("\n", " ") for c in row.cells]
        if not cells:
            continue
        label = cells[0].strip()
        if not label:
            continue
        if not is_publishable_statement_line(label=label):
            continue
        low = label.lower()
        header_blob = " ".join(cells).lower()
        if low == "activo" and "nota" in header_blob:
            continue
        if ("patrimonio" in low or low == "pasivo") and "nota" in header_blob:
            continue

        amounts = _extract_amount_pair(cells)
        if amounts is None:
            continue
        n, n1 = amounts
        note = _parse_note_refs(cells[2] if len(cells) > 2 else "")
        bold = _cell_bold(row.cells[0])
        rows_out.append(_RawBalanceRow(label=label, note_refs=note, n=n, n1=n1, bold=bold))
    return rows_out


def _is_total(label: str) -> bool:
    return bool(_TOTAL_RE.match(label))


def _amounts_match(a: float, b: float, tol: float = 0.05) -> bool:
    return abs(a - b) <= tol


def _find_children(
    i: int,
    rows: list[_RawBalanceRow],
    child_of: dict[int, int],
) -> list[int]:
    parent = rows[i]
    if _is_total(parent.label):
        return []
    if abs(parent.n) < 0.005 and abs(parent.n1) < 0.005:
        return []

    kids: list[int] = []
    acc_n = 0.0
    acc_n1 = 0.0
    j = i + 1
    while j < len(rows):
        if _is_total(rows[j].label):
            break
        if j in child_of:
            if child_of[j] in kids:
                j += 1
                continue
            break

        candidate = rows[j]
        next_n = acc_n + candidate.n
        next_n1 = acc_n1 + candidate.n1
        overshoot_n = abs(parent.n) > 0.005 and abs(next_n) > abs(parent.n) + 0.05
        overshoot_n1 = abs(parent.n1) > 0.005 and abs(next_n1) > abs(parent.n1) + 0.05
        if kids and overshoot_n and overshoot_n1:
            break

        kids.append(j)
        acc_n, acc_n1 = next_n, next_n1
        if _amounts_match(acc_n, parent.n) and _amounts_match(acc_n1, parent.n1):
            return kids
        j += 1

    if kids and _amounts_match(acc_n, parent.n) and _amounts_match(acc_n1, parent.n1):
        return kids
    return []


def assign_hierarchy(rows: list[_RawBalanceRow]) -> list[BalanceLine]:
    child_of: dict[int, int] = {}
    for i in range(len(rows) - 1, -1, -1):
        if i in child_of:
            continue
        for j in _find_children(i, rows, child_of):
            child_of[j] = i

    used_ids: set[str] = set()
    index_to_id: dict[int, str] = {}
    for i, row in enumerate(rows):
        base = _slugify(row.label) or f"line_{i}"
        line_id = base
        n = 2
        while line_id in used_ids:
            line_id = f"{base}_{n}"
            n += 1
        used_ids.add(line_id)
        index_to_id[i] = line_id

    has_children = {
        i for i in range(len(rows)) if any(child_of.get(j) == i for j in range(len(rows)))
    }
    lines: list[BalanceLine] = []

    for i, row in enumerate(rows):
        label = row.label
        parent = index_to_id[child_of[i]] if i in child_of else None

        if _TOTAL_FINAL_ASSET.match(label) or _TOTAL_FINAL_EQUITY.match(label):
            role, level = "total", 1
            parent = None
        elif _is_total(label) or row.bold:
            role, level = "subtotal", 1
            parent = None
        elif i in has_children and i in child_of:
            role, level = "subtotal_group", 2
        elif i in has_children:
            role, level = "subtotal_group", 1
        elif i in child_of:
            role, level = "detail", 2
        else:
            role, level = "detail", 1

        lines.append(
            BalanceLine(
                id=index_to_id[i],
                label=label,
                level=level,
                parent=parent,
                note_refs=row.note_refs,
                n=row.n,
                n1=row.n1,
                role=role,  # type: ignore[arg-type]
                section="asset",
            )
        )
    return lines


def extract_balance_lines_from_table(tbl: object, section: str) -> list[BalanceLine]:
    raw = parse_balance_table_rows(tbl)
    if len(raw) < 2:
        return []
    lines = assign_hierarchy(raw)
    for ln in lines:
        ln.section = section  # type: ignore[assignment]
    return lines


def classify_balance_table(tbl: object) -> str | None:
    """Return 'asset', 'equity_liability', or None."""
    if not getattr(tbl, "rows", None) or not tbl.rows:
        return None
    cells = [c.text.strip() for c in tbl.rows[0].cells]
    if not cells:
        return None
    label = cells[0]
    low = label.lower()
    if low == "activo" or (low.startswith("activo") and "pasivo" not in low):
        return "asset"
    if "patrimonio" in low or ("pasivo" in low and "activo" not in low):
        return "equity_liability"
    return None
