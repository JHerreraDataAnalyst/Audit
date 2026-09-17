"""
Improve N-1 matching from Claude CSV using aliases for V5 abbreviated labels.
Then adapt PGF memoria notes (entity, years, hide empty notes).
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

from app.domain.content import ContentBlock, ContentModel
from app.services.docx_export import export_docx
from app.services.storage import load_content, load_finance, load_project, save_content, save_finance
from app.domain.validation import validate_balance

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

# Map normalized finance labels / fragments -> preferred CSV-normalized keys
ALIASES: dict[str, str] = {
    "instal tecnicas y otro inmov materia": "inmovilizado material",
    "inversiones financieras a l p": "inversiones financieras a largo plazo",
    "inversiones financieras a c p": "inversiones financieras a corto plazo",
    "invers empresas grupo y asociadas a c p": "inversiones en empresas del grupo y asociadas a corto plazo",
    "invers empresas grupo y asociadas a l p": "inversiones en empresas del grupo y asociadas a largo plazo",
    "creditos a terceros": "inversiones financieras a largo plazo",
    "creditos a empresas": "creditos a empresas",
    "otros activos financieros": "otros activos financieros",
    "productos terminados": "existencias",
    "de ciclo corto de produccion": "existencias",
    "clientes ventas y prestaciones servici": "clientes por ventas y prestaciones de servicios",
    "clientes vtas y prest serv a c p": "clientes por ventas y prestaciones de servicios a corto plazo",
    "otros creditos con las admin publicas": "otros deudores",
    "tesoreria": "efectivo y otros activos liquidos equivalentes",
    "efectivo y otros activos liquidos equivalentes": "efectivo y otros activos liquidos equivalentes",
    "legal y estatutarias": "otras reservas",
    "cuenta perdidas y ganancias 129": "resultado del ejercicio",
    "resultado del ejercicio": "resultado del ejercicio",
    "deudas a l p": "deudas a largo plazo",
    "deudas a c p": "deudas a corto plazo",
    "otros pasivos financieros": "otros pasivos financieros",
    "acreedores ciales y otras ctas a pag": "acreedores comerciales y otras cuentas a pagar",
    "proveedores empresas del grupo y as": "acreedores comerciales y otras cuentas a pagar",
    "acreedores varios": "acreedores comerciales y otras cuentas a pagar",
    "otras deudas con las admin publicas": "acreedores comerciales y otras cuentas a pagar",
    "instrumentos de patrimonio": "instrumentos de patrimonio",
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
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = t.replace("l/p", "largo plazo").replace("c/p", "corto plazo")
    t = t.replace("a)", " ").replace("b)", " ").replace("c)", " ")
    t = re.sub(r"\b[a-z]-?\d+(?:\.\d+)*\b", " ", t)
    t = re.sub(r"\b[ivxlcdm]+\.\b", " ", t)
    t = re.sub(r"\b\d+(?:\.\d+)*\b", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = t.replace("ciales", "comerciales").replace("ctas", "cuentas").replace("vtas", "ventas")
    t = t.replace("prest serv", "prestaciones servicios").replace("admin", "administraciones")
    return ALIASES.get(t, t)


def load_csv() -> dict[str, dict[str, list[dict]]]:
    out: dict[str, dict[str, list[dict]]] = {}
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            soc = (row.get("sociedad") or "").strip().upper()
            estado = (row.get("estado") or "").strip()
            out.setdefault(soc, {}).setdefault(estado, []).append(row)
    return out


def index_candidates(rows: list[dict]) -> list[tuple[str, float]]:
    return [(norm(r["epigrafe"]), parse_es_amount(r["importe_2024"])) for r in rows]


def match_amount(label: str, candidates: list[tuple[str, float]]) -> float | None:
    target = norm(label)
    if not target:
        return None
    # exact
    for cand, amount in candidates:
        if cand == target:
            return amount
    # alias already applied via norm; try contains
    best = None
    best_score = 0
    tset = set(target.split())
    for cand, amount in candidates:
        if not cand:
            continue
        if target in cand or cand in target:
            score = min(len(target), len(cand))
            if score > best_score:
                best_score = score
                best = amount
            continue
        cset = set(cand.split())
        if not tset or not cset:
            continue
        inter = tset & cset
        score_r = len(inter) / max(len(tset), len(cset))
        if score_r >= 0.8 and len(inter) >= 2 and score_r > best_score:
            best_score = score_r
            best = amount
    return best


def refine_n1_all() -> None:
    data = load_csv()
    for soc, project_id in PROJECTS.items():
        finance = load_finance(project_id)
        bal = index_candidates(data.get(soc, {}).get("Balance", []))
        pyg = index_candidates(data.get(soc, {}).get("PyG", []))
        mb = mp = 0
        for ln in finance.statements.balance.lines:
            amt = match_amount(ln.label, bal)
            if amt is not None:
                ln.n1 = amt
                mb += 1
        for ln in finance.statements.pyg.lines:
            amt = match_amount(ln.label, pyg)
            if amt is not None:
                ln.n1 = amt
                mp += 1
        save_finance(project_id, finance)
        gaps = sum(1 for ln in finance.statements.balance.lines if abs(ln.n) > 0.005 and abs(ln.n1) < 0.005)
        tot = next((ln.n1 for ln in finance.statements.balance.lines if "TOTAL ACTIVO" in ln.label.upper()), 0)
        print(f"{soc}: matched Bal={mb} PyG={mp} | gaps N>0 N1=0: {gaps} | TOTAL ACTIVO N1={tot:,.2f}")


def _shift_years(text: str) -> str:
    """Shift comparative narrative: 2024->2025, 2023->2024 for ejercicio actual."""
    # Protect already-shifted markers via placeholders
    text = text.replace("2025", "§Y5§")
    text = text.replace("2024", "§Y4§")
    text = text.replace("2023", "§Y3§")
    text = text.replace("§Y4§", "2025")
    text = text.replace("§Y3§", "2024")
    text = text.replace("§Y5§", "2025")  # keep prior 2025 mentions
    return text


def adapt_pgf_notes() -> None:
    pid = PROJECTS["PGF"]
    project = load_project(pid)
    finance = load_finance(pid)
    content = load_content(pid)

    legal = project.entity.legal_name
    # Sums to decide which notes to hide
    def sum_labels(*needles: str) -> float:
        total = 0.0
        for ln in finance.statements.balance.lines:
            up = ln.label.upper()
            if any(n.upper() in up for n in needles):
                total += abs(ln.n) + abs(ln.n1)
        return total

    hide_sections: set[str] = set()
    if sum_labels("INMOVILIZADO INTANGIBLE") < 0.01:
        hide_sections.add("nota_5")
    if sum_labels("INVERSIONES INMOBILIARIAS") < 0.01:
        hide_sections.add("nota_7")
    if sum_labels("ARRENDAMIENTO") < 0.01:
        hide_sections.add("nota_8")

    new_blocks: list[ContentBlock] = []
    for b in content.blocks:
        nb = b.model_copy(deep=True)
        if nb.section in hide_sections:
            nb.visible = False
        # entity rename in visible narrative
        if "INMOBILIARIA CORRAL" in nb.text.upper():
            nb.text = re.sub(
                r"Inmobiliaria Corral,\s*S\.?L\.?",
                legal,
                nb.text,
                flags=re.IGNORECASE,
            )
            nb.text = re.sub(
                r"INMOBILIARIA CORRAL,\s*S\.?L\.?",
                legal,
                nb.text,
                flags=re.IGNORECASE,
            )
        if nb.kind in {"paragraph", "heading1", "heading2", "list_item", "title"}:
            nb.text = _shift_years(nb.text)
        new_blocks.append(nb)

    # Refresh bootstrap banner
    banner_text = (
        f"Memoria de trabajo — {legal}. Ejercicio terminado el 31 de diciembre de 2025 "
        f"(comparativo 2024). Cifras N desde BALANCES GRUPO V5; N-1 desde OCR CCAA 2024. "
        f"Notas adaptadas desde plantilla de referencia; secciones sin saldo ocultas: "
        f"{', '.join(sorted(hide_sections)) or 'ninguna'}."
    )
    found_banner = False
    for b in new_blocks:
        if b.id == "p.bootstrap_corral_banner":
            b.text = banner_text
            b.visible = True
            found_banner = True
            break
    if not found_banner:
        new_blocks.insert(
            0,
            ContentBlock(
                id="p.bootstrap_corral_banner",
                kind="paragraph",
                text=banner_text,
                section="nota_1",
                visible=True,
            ),
        )

    # Ensure nota_1 intro mentions PGF activity briefly
    intro = ContentBlock(
        id="p.pgf_actividad_intro",
        kind="paragraph",
        text=(
            f"{legal} (NIF B81057200) forma parte del Grupo Inmobiliaria Corral. "
            "Su actividad principal se enmarca en la promoción inmobiliaria. "
            "Las presentes cuentas anuales corresponden al ejercicio anual terminado "
            "el 31 de diciembre de 2025, presentándose cifras comparativas del ejercicio 2024."
        ),
        section="nota_1",
        visible=True,
    )
    # insert after first heading1
    out: list[ContentBlock] = []
    inserted = False
    for b in new_blocks:
        if b.id == "p.pgf_actividad_intro":
            continue
        out.append(b)
        if not inserted and b.kind == "heading1":
            out.append(intro)
            inserted = True
    if not inserted:
        out.insert(0, intro)

    content = ContentModel(blocks=out)
    save_content(pid, content)

    # Export word draft
    out_docx = (
        ROOT
        / "clientes"
        / "INMOBILIARIA CORRAL, S.L"
        / "02_Trabajo_informes"
        / "PGF_CCAA_2025_borrador.docx"
    )
    out_docx.parent.mkdir(parents=True, exist_ok=True)
    export_docx(project, finance, content, out_docx)
    res = validate_balance(finance)
    visible = sum(1 for b in content.blocks if b.visible)
    hidden = sum(1 for b in content.blocks if not b.visible)
    print(
        f"PGF notes: visible={visible} hidden={hidden} hide_sections={sorted(hide_sections)} | "
        f"balance_ok={res.ok} | Word -> {out_docx}"
    )


def main() -> None:
    print("=== 1) Afinar N-1 ===")
    refine_n1_all()
    print("=== 2) Adaptar notas PGF ===")
    adapt_pgf_notes()


if __name__ == "__main__":
    main()
