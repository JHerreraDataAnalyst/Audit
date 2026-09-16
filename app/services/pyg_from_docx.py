"""
Extract typed PyG (Cuenta de pérdidas y ganancias) from a CCAA DOCX table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.finance import PygLine


_NOTE_SPLIT = re.compile(r"\s*(?:,|;| y | Y )\s*")
_RESULT_TOTAL = re.compile(r"^\s*resultado\s+del\s+ejercicio\b", re.I)
_RESULT_SUB = re.compile(
    r"^\s*resultado\s+(de\s+explotaci[oó]n|financiero|antes\s+de\s+impuestos)\b",
    re.I,
)
_HEADER_SECTION = re.compile(
    r"operaciones\s+continuadas|operaciones\s+interrumpidas|a\)\s*operaciones",
    re.I,
)
_PYG_HINT = re.compile(
    r"importe\s+neto\s+de\s+la\s+cifra|p[eé]rdidas\s+y\s+ganancias|"
    r"resultado\s+de\s+explotaci[oó]n|aprovisionamientos",
    re.I,
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

    # Fix rare Word typos like 614,711,00 → 614.711,00
    if clean.count(",") >= 2 and "." not in clean:
        parts = clean.split(",")
        clean = ".".join(parts[:-1]) + "," + parts[-1]

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
    return slug[:50] if slug else "pyg_line"


def _parse_note_refs(text: str) -> list[str]:
    clean = text.strip()
    if not clean or clean in {"-", "–", "—"}:
        return []
    return [p.strip() for p in _NOTE_SPLIT.split(clean) if p.strip()]


@dataclass
class _RawPygRow:
    label: str
    note_refs: list[str]
    n: float
    n1: float
    is_header: bool = False


def _extract_amounts(cells: list[str]) -> tuple[float | None, float | None]:
    """Return (n, n1). None means no amount cell present."""
    if len(cells) >= 6:
        raw_n, raw_n1 = cells[-2].strip(), cells[-1].strip()
        if not raw_n and not raw_n1:
            return None, None
        n = 0.0 if raw_n in {"-", "–", "—", ""} else _parse_spanish_number(raw_n)
        n1 = 0.0 if raw_n1 in {"-", "–", "—", ""} else _parse_spanish_number(raw_n1)
        if n is None and n1 is None and raw_n not in {"-", "–", "—"} and raw_n1 not in {"-", "–", "—"}:
            return None, None
        return (0.0 if n is None and raw_n in {"-", "–", "—", ""} else (n or 0.0),
                0.0 if n1 is None and raw_n1 in {"-", "–", "—", ""} else (n1 or 0.0))

    nums: list[float] = []
    for c in cells[1:]:
        if c.strip() in {"-", "–", "—"}:
            nums.append(0.0)
            continue
        v = _parse_spanish_number(c)
        if v is not None:
            nums.append(v)
    if len(nums) >= 2:
        return nums[-2], nums[-1]
    if len(nums) == 1:
        return nums[0], 0.0
    return None, None


def parse_pyg_table_rows(tbl: object) -> list[_RawPygRow]:
    rows_out: list[_RawPygRow] = []
    for row in tbl.rows:  # type: ignore[attr-defined]
        cells = [c.text.strip().replace("\n", " ") for c in row.cells]
        if not any(cells):
            continue
        label = cells[0].strip()
        blob = " ".join(cells).lower()
        if not label and "nota" in blob and "ejercicio" in blob:
            continue
        if not label:
            continue
        if label.lower() in {"nota"} or (not label and "ejercicio" in blob):
            continue

        n, n1 = _extract_amounts(cells)
        note = _parse_note_refs(cells[2] if len(cells) > 2 else "")

        if n is None and n1 is None:
            if _HEADER_SECTION.search(label) or label.isupper():
                rows_out.append(_RawPygRow(label=label, note_refs=[], n=0.0, n1=0.0, is_header=True))
            continue

        rows_out.append(_RawPygRow(label=label, note_refs=note, n=n or 0.0, n1=n1 or 0.0))
    return rows_out


def _amounts_match(a: float, b: float, tol: float = 0.05) -> bool:
    return abs(a - b) <= tol


def _is_result_line(label: str) -> bool:
    return bool(_RESULT_TOTAL.match(label) or _RESULT_SUB.match(label))


def _find_children(i: int, rows: list[_RawPygRow], child_of: dict[int, int]) -> list[int]:
    parent = rows[i]
    if parent.is_header or _is_result_line(parent.label):
        return []
    if abs(parent.n) < 0.005 and abs(parent.n1) < 0.005:
        return []

    kids: list[int] = []
    acc_n = acc_n1 = 0.0
    j = i + 1
    while j < len(rows):
        if rows[j].is_header or _is_result_line(rows[j].label):
            break
        if j in child_of:
            if child_of[j] in kids:
                j += 1
                continue
            break

        cand = rows[j]
        next_n = abs(acc_n) + abs(cand.n)  # signs often align within a group
        # Prefer signed sum for matching parent
        signed_n = acc_n + cand.n
        signed_n1 = acc_n1 + cand.n1
        overshoot = (
            abs(parent.n) > 0.005 and abs(signed_n) > abs(parent.n) + 0.05
            and abs(parent.n1) > 0.005 and abs(signed_n1) > abs(parent.n1) + 0.05
        )
        if kids and overshoot:
            break

        kids.append(j)
        acc_n, acc_n1 = signed_n, signed_n1
        if _amounts_match(acc_n, parent.n) and _amounts_match(acc_n1, parent.n1):
            return kids
        j += 1
        _ = next_n

    if kids and _amounts_match(acc_n, parent.n) and _amounts_match(acc_n1, parent.n1):
        return kids
    return []


def assign_hierarchy(rows: list[_RawPygRow]) -> list[PygLine]:
    child_of: dict[int, int] = {}
    for i in range(len(rows) - 1, -1, -1):
        if i in child_of or rows[i].is_header:
            continue
        for j in _find_children(i, rows, child_of):
            child_of[j] = i

    used_ids: set[str] = set()
    index_to_id: dict[int, str] = {}
    for i, row in enumerate(rows):
        base = _slugify(row.label) or f"pyg_{i}"
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
    lines: list[PygLine] = []
    for i, row in enumerate(rows):
        parent = index_to_id[child_of[i]] if i in child_of else None
        if row.is_header:
            role, level, parent = "header", 1, None
        elif _RESULT_TOTAL.match(row.label):
            role, level, parent = "total", 1, None
        elif _RESULT_SUB.match(row.label):
            role, level, parent = "subtotal", 1, None
        elif i in has_children and i in child_of:
            role, level = "subtotal_group", 2
        elif i in has_children:
            role, level = "subtotal_group", 1
        elif i in child_of:
            role, level = "detail", 2
        else:
            role, level = "detail", 1

        lines.append(
            PygLine(
                id=index_to_id[i],
                label=row.label,
                level=level,
                parent=parent,
                note_refs=row.note_refs,
                n=row.n,
                n1=row.n1,
                role=role,  # type: ignore[arg-type]
            )
        )
    return lines


def classify_pyg_table(tbl: object) -> bool:
    if not getattr(tbl, "rows", None) or len(tbl.rows) < 5:
        return False
    sample = []
    for row in list(tbl.rows)[:12]:
        sample.append(" ".join(c.text for c in row.cells))
    blob = "\n".join(sample)
    if classify_looks_like_balance(blob):
        return False
    return bool(_PYG_HINT.search(blob))


def classify_looks_like_balance(blob: str) -> bool:
    low = blob.lower()
    return ("activo" in low and "nota" in low) or ("patrimonio neto" in low and "pasivo" in low)


def extract_pyg_lines_from_table(tbl: object) -> list[PygLine]:
    raw = parse_pyg_table_rows(tbl)
    data_rows = [r for r in raw if not r.is_header]
    if len(data_rows) < 3:
        return []
    return assign_hierarchy(raw)


def infer_income_fact(lines: list[PygLine]) -> float | None:
    for ln in lines:
        if "importe neto" in ln.label.lower() and "cifra" in ln.label.lower():
            return ln.n
    return None
