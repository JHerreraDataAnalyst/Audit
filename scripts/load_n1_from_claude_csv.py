"""
Load Claude OCR CSV (CCAA 2024) as N-1 into Corral small-entity projects.
Keeps existing N (2025) amounts; only fills n1 via epigrafe matching.
"""

from __future__ import annotations

import csv
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.domain.validation import validate_balance
from app.services.storage import load_finance, save_finance

CSV_PATH = (
    ROOT
    / "clientes"
    / "INMOBILIARIA CORRAL, S.L"
    / "03_OCR_Claude_CCAA_2024"
    / "CCAA_2024_balance_pyg_extraido.csv"
)

PROJECTS = {
    "PGF": "pgf-promociones-gran-ferial",
    "PBP": "pbp-promociones-barrio-puerto",
    "CCA": "cca-coslada-coches-alquiler",
    "AUTOTYPE": "autotype-sl",
}


def parse_es_amount(raw: str | None) -> float:
    if raw is None or str(raw).strip() == "":
        return 0.0
    s = str(raw).strip().replace(".", "").replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return 0.0


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = t.replace("a)", "").replace("b)", "")
    t = re.sub(r"^[a-z]-?\d+(\.\d+)*\s*", "", t)  # A-1.I.1 / A.I /
    t = re.sub(r"^[ivxlcdm]+\.\s*", "", t)
    t = re.sub(r"^\d+(\.\d+)*\s*", "", t)
    t = re.sub(r"^[a-z]\)\s*", "", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # common abbreviations
    repl = {
        "activo liquidos equivalentes": "efectivo y otros activos liquidos equivalentes",
        "activo liquido equivalentes": "efectivo y otros activos liquidos equivalentes",
        "deudores ciales y otras ctas a cobrar": "deudores comerciales y otras cuentas a cobrar",
        "deudores comerciales y otras cuentas a cobrar": "deudores comerciales y otras cuentas a cobrar",
        "invers empresas grupo y asociadas a l p": "inversiones en empresas del grupo y asociadas a largo plazo",
        "inversiones en empresas del grupo y asociadas a largo plazo": "inversiones en empresas del grupo y asociadas a largo plazo",
        "total activo a b": "total activo",
        "total activo a b ": "total activo",
        "total patrimonio neto y pasivo a b c": "total patrimonio neto y pasivo",
        "resultado del ejercicio procedente de operaciones continuadas a 3 24": "resultado del ejercicio",
        "a 5 resultado consolidado del ejercicio a 4 25": "resultado del ejercicio",
        "a resultado de la cuenta de perdidas y ganancias": "resultado del ejercicio",
    }
    return repl.get(t, t)


def load_csv_by_sociedad() -> dict[str, dict[str, list[dict]]]:
    out: dict[str, dict[str, list[dict]]] = {}
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            soc = (row.get("sociedad") or "").strip().upper()
            estado = (row.get("estado") or "").strip()
            out.setdefault(soc, {}).setdefault(estado, []).append(row)
    return out


def best_match(label: str, candidates: list[tuple[str, float]]) -> tuple[float | None, str | None]:
    """Return (amount, matched_norm) for best normalized label match."""
    target = norm(label)
    if not target:
        return None, None

    # exact
    for cand_label, amount in candidates:
        if cand_label == target:
            return amount, cand_label

    # contains / contained (prefer longer overlap)
    best = None
    best_score = 0
    for cand_label, amount in candidates:
        if not cand_label:
            continue
        if target in cand_label or cand_label in target:
            score = min(len(target), len(cand_label))
            if score > best_score:
                best_score = score
                best = (amount, cand_label)
    if best and best_score >= 12:
        return best

    # token overlap
    tset = set(target.split())
    for cand_label, amount in candidates:
        cset = set(cand_label.split())
        if not tset or not cset:
            continue
        inter = tset & cset
        score = len(inter) / max(len(tset), len(cset))
        if score >= 0.85 and len(inter) >= 2:
            if best is None or score > best_score:
                best_score = score
                best = (amount, cand_label)
    if best:
        return best
    return None, None


def apply_n1(project_id: str, rows_balance: list[dict], rows_pyg: list[dict]) -> dict:
    finance = load_finance(project_id)

    bal_cands = [
        (norm(r["epigrafe"]), parse_es_amount(r["importe_2024"]))
        for r in rows_balance
    ]
    pyg_cands = [
        (norm(r["epigrafe"]), parse_es_amount(r["importe_2024"]))
        for r in rows_pyg
    ]

    matched_bal = 0
    for ln in finance.statements.balance.lines:
        amount, _ = best_match(ln.label, bal_cands)
        if amount is not None:
            ln.n1 = amount
            matched_bal += 1

    matched_pyg = 0
    for ln in finance.statements.pyg.lines:
        amount, _ = best_match(ln.label, pyg_cands)
        if amount is not None:
            ln.n1 = amount
            matched_pyg += 1

    save_finance(project_id, finance)
    res = validate_balance(finance)

    # Totals for report
    tot_n = finance.total_assets_n()
    tot_n1_assets = sum(
        ln.n1 for ln in finance.statements.balance.lines if ln.section == "asset" and ln.role == "total"
    )
    if not tot_n1_assets:
        # fallback: max TOTAL ACTIVO line n1
        for ln in finance.statements.balance.lines:
            if "TOTAL ACTIVO" in ln.label.upper():
                tot_n1_assets = ln.n1
                break

    csv_total = next(
        (parse_es_amount(r["importe_2024"]) for r in rows_balance if "TOTAL ACTIVO" in r["epigrafe"].upper()),
        None,
    )

    return {
        "project_id": project_id,
        "matched_balance": matched_bal,
        "matched_pyg": matched_pyg,
        "assets_n": tot_n,
        "assets_n1_line": tot_n1_assets,
        "csv_total_activo_2024": csv_total,
        "balance_ok_n": res.ok,
    }


def main() -> None:
    data = load_csv_by_sociedad()
    print(f"CSV: {CSV_PATH}")
    for soc, project_id in PROJECTS.items():
        bal = data.get(soc, {}).get("Balance", [])
        pyg = data.get(soc, {}).get("PyG", [])
        if not bal:
            print(f"{soc}: NO DATA")
            continue
        info = apply_n1(project_id, bal, pyg)
        print(
            f"{soc} -> {project_id} | "
            f"match Bal {info['matched_balance']} PyG {info['matched_pyg']} | "
            f"Activo N={info['assets_n']:,.2f} | "
            f"N-1 TOTAL ACTIVO linea={info['assets_n1_line']:,.2f} "
            f"(CSV {info['csv_total_activo_2024']:,.2f}) | "
            f"cuadre N={'OK' if info['balance_ok_n'] else 'FAIL'}"
        )


if __name__ == "__main__":
    main()
