"""
Rebuild memoria content for Corral small entities (PGF, PBP, CCA, AUTOTYPE).

Best practice: notes driven by balances; pending items highlighted yellow
and marked SOLICITAR when 2025 source docs are missing in the client folder.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.domain.content import ContentBlock, ContentModel
from app.domain.finance import FinanceTable, TableCell, TableColumn
from app.domain.validation import validate_balance
from app.services.docx_export import export_docx
from app.services.formatting import format_amount
from app.services.storage import load_finance, load_project, save_content, save_finance

ENTITIES = {
    "pgf-promociones-gran-ferial": {
        "short": "PGF",
        "nif": "B81057200",
        "activity": (
            "desarrolla su actividad en el ámbito de la promoción inmobiliaria."
        ),
        "word": "PGF_CCAA_2025_borrador.docx",
        # Folder check results for 2025:
        "plantilla_2025": False,  # only PROMEDIO PLANTILLA 2024 (periodo 2024)
        "pmp_2025": False,  # only PMP 2024 group workbook
        "fiscal_fino_2025": False,  # sábanas grupo / sin liquidación individual 2025 cerrada
        "note_plantilla_2024": "Existe PROMEDIO PLANTILLA 2024 (periodo 01/01/2024-31/12/2024) para Gran Ferial; no hay listado de plantilla media del ejercicio 2025.",
        "note_pmp_2024": "Existe cálculo PMP 2024 a nivel grupo (incluye PGFC); no hay cálculo PMP del ejercicio 2025.",
        "note_fiscal": "Hay sábanas fiscales de consolidación 2025 y papeles IS 2024 de grupo; falta contraste fiscal fino individual 2025 (liquidación/modelo y cuadre con PyG).",
    },
    "pbp-promociones-barrio-puerto": {
        "short": "PBP",
        "nif": "B28069656",
        "activity": (
            "desarrolla su actividad en el ámbito de la promoción inmobiliaria."
        ),
        "word": "PBP_CCAA_2025_borrador.docx",
        "plantilla_2025": False,
        "pmp_2025": False,
        "fiscal_fino_2025": False,
        "note_plantilla_2024": "Existe PROMEDIO PLANTILLA 2024 (periodo 2024) para Barrio del Puerto; no hay listado de plantilla media del ejercicio 2025.",
        "note_pmp_2024": "Existe cálculo PMP 2024 a nivel grupo (incluye PBPC); no hay cálculo PMP del ejercicio 2025.",
        "note_fiscal": "Hay sábanas fiscales de consolidación 2025 y papeles IS 2024 de grupo; falta contraste fiscal fino individual 2025.",
    },
    "cca-coslada-coches-alquiler": {
        "short": "CCA",
        "nif": "B825XXXXX",  # will override from known if needed
        "activity": (
            "desarrolla su actividad principalmente en el alquiler de vehículos "
            "y servicios relacionados."
        ),
        "word": "CCA_CCAA_2025_borrador.docx",
        "plantilla_2025": False,
        "pmp_2025": False,
        "fiscal_fino_2025": False,
        "note_plantilla_2024": "No consta en la carpeta del cliente un listado de plantilla media 2025 (ni 2024) identificable para Coslada Coches de Alquiler.",
        "note_pmp_2024": "No consta cálculo PMP 2025 (ni claro 2024) individual para Coslada Coches de Alquiler en la carpeta revisada.",
        "note_fiscal": "Existe MODELO 200 2024 de CC Alquiler; falta contraste fiscal fino del ejercicio 2025 (liquidación/cuadre con PyG).",
    },
    "autotype-sl": {
        "short": "AUTOTYPE",
        "nif": "BXXXXXXXX",
        "activity": (
            "figura como sociedad del Grupo; en los ejercicios recientes su actividad "
            "operativa aparece residual / inactiva a efectos de la cuenta de resultados."
        ),
        "word": "AUTOTYPE_CCAA_2025_borrador.docx",
        "plantilla_2025": False,
        "pmp_2025": False,
        "fiscal_fino_2025": False,
        "note_plantilla_2024": "No consta listado de plantilla media 2025 (ni 2024) para Autotype en la carpeta revisada.",
        "note_pmp_2024": "No consta cálculo PMP 2025 para Autotype en la carpeta revisada.",
        "note_fiscal": "Existe MODELO 200 2024 de Autotype; falta contraste fiscal fino del ejercicio 2025.",
    },
}

# Correct NIFs from V5 / prior knowledge
NIFS = {
    "pgf-promociones-gran-ferial": "B81057200",
    "pbp-promociones-barrio-puerto": "B28069656",
    "cca-coslada-coches-alquiler": "B81139818",
    "autotype-sl": "B83414672",
}


def _amt(v: float) -> str:
    return format_amount(v, zero_as_dash=False)


def _cell(value: str = "", numeric: float | None = None, bold: bool = False, is_total: bool = False) -> TableCell:
    if numeric is not None and not value:
        value = _amt(numeric)
    return TableCell(value=value, numeric=numeric, bold=bold, is_total=is_total)


def _amount_cols() -> list[TableColumn]:
    return [
        TableColumn(id="concepto", header="", align="left", is_amount=False),
        TableColumn(id="n", header="31.12.2025", align="right", is_amount=True),
        TableColumn(id="n1", header="31.12.2024", align="right", is_amount=True),
    ]


def _row(concepto: str, n: float, n1: float, *, bold: bool = False, total: bool = False) -> dict[str, TableCell]:
    return {
        "concepto": _cell(concepto, bold=bold or total),
        "n": _cell(numeric=n, bold=bold or total, is_total=total),
        "n1": _cell(numeric=n1, bold=bold or total, is_total=total),
    }


def _find_balance(finance, *needles: str) -> tuple[float, float]:
    for ln in finance.statements.balance.lines:
        lab = ln.label.casefold()
        if all(n.casefold() in lab for n in needles):
            return ln.n, ln.n1
    return 0.0, 0.0


def _resultado(finance) -> tuple[float, float]:
    for ln in finance.statements.balance.lines:
        if ln.label.strip().startswith("VII.") and "Resultado" in ln.label:
            return ln.n, ln.n1
    return _find_balance(finance, "Resultado del ejercicio")


def build_tables(finance) -> dict[str, FinanceTable]:
    imm_n, imm_n1 = _find_balance(finance, "Inmovilizado Material")
    det_n, det_n1 = _find_balance(finance, "Instal")
    if abs(det_n) + abs(det_n1) > abs(imm_n) + abs(imm_n1):
        imm_n, imm_n1 = det_n, det_n1

    inv_imm_n, inv_imm_n1 = _find_balance(finance, "Inversiones inmobiliarias")
    # Prefer subtotal group line
    for ln in finance.statements.balance.lines:
        if ln.label.strip().startswith("III.") and "Inversiones inmobiliarias" in ln.label:
            inv_imm_n, inv_imm_n1 = ln.n, ln.n1
            break

    cred_lp_n, cred_lp_n1 = _find_balance(finance, "Inversiones financieras a L")
    for ln in finance.statements.balance.lines:
        if "Créditos a terceros" in ln.label or "Creditos a terceros" in ln.label.replace("é", "e"):
            if "L" in ln.label or "largo" in ln.label.casefold() or ln.level >= 3:
                # prefer detail credits if material
                if abs(ln.n) + abs(ln.n1) > 0:
                    cred_lp_n, cred_lp_n1 = ln.n, ln.n1
                    break
    # simpler: V. Inversiones financieras a L/P subtotal
    for ln in finance.statements.balance.lines:
        if ln.label.strip().startswith("V.") and "Inversiones financieras a L" in ln.label:
            cred_lp_n, cred_lp_n1 = ln.n, ln.n1
            break

    inv_cp_n, inv_cp_n1 = 0.0, 0.0
    for ln in finance.statements.balance.lines:
        if ln.label.strip().startswith("V.") and "Inversiones financieras a C" in ln.label:
            inv_cp_n, inv_cp_n1 = ln.n, ln.n1
            break
    grupo_cp_n, grupo_cp_n1 = 0.0, 0.0
    for ln in finance.statements.balance.lines:
        if "empresas grupo y asociadas a C" in ln.label.casefold() or (
            ln.label.strip().startswith("IV.") and "grupo" in ln.label.casefold() and "C/P" in ln.label
        ):
            grupo_cp_n, grupo_cp_n1 = ln.n, ln.n1
            break

    exist_n, exist_n1 = 0.0, 0.0
    for ln in finance.statements.balance.lines:
        if ln.label.strip().startswith("II.") and "Existencias" in ln.label:
            exist_n, exist_n1 = ln.n, ln.n1
            break
    deud_n, deud_n1 = 0.0, 0.0
    for ln in finance.statements.balance.lines:
        if "Deudores" in ln.label and "cobrar" in ln.label.casefold():
            deud_n, deud_n1 = ln.n, ln.n1
            break
    efec_n, efec_n1 = 0.0, 0.0
    for ln in finance.statements.balance.lines:
        if "Efectivo" in ln.label or "Tesorer" in ln.label:
            if ln.role in {"subtotal_group", "subtotal", "detail"}:
                efec_n, efec_n1 = ln.n, ln.n1
                if "Efectivo" in ln.label:
                    break

    cap_n, cap_n1 = _find_balance(finance, "Capital escriturado")
    res_n, res_n1 = _find_balance(finance, "Otras reservas")
    legal_n, legal_n1 = _find_balance(finance, "Legal y estatutarias")
    aport_n, aport_n1 = _find_balance(finance, "Otras aportaciones de socios")
    rdo_n, rdo_n1 = _resultado(finance)

    deudas_lp_n, deudas_lp_n1 = 0.0, 0.0
    for ln in finance.statements.balance.lines:
        if ln.label.strip().startswith("II.") and "Deudas a L" in ln.label:
            deudas_lp_n, deudas_lp_n1 = ln.n, ln.n1
            break
    deudas_cp_n, deudas_cp_n1 = 0.0, 0.0
    for ln in finance.statements.balance.lines:
        if ln.label.strip().startswith("III.") and "Deudas a C" in ln.label:
            deudas_cp_n, deudas_cp_n1 = ln.n, ln.n1
            break
    acree_n, acree_n1 = 0.0, 0.0
    for ln in finance.statements.balance.lines:
        if "Acreedores" in ln.label and "pag" in ln.label.casefold():
            acree_n, acree_n1 = ln.n, ln.n1
            break

    aid_n, aid_n1 = _find_balance(finance, "Activos por impuesto diferido")
    pid_n, pid_n1 = _find_balance(finance, "Pasivos por impuesto diferido")

    tables: dict[str, FinanceTable] = {
        "t_aplicacion_resultado": FinanceTable(
            id="t_aplicacion_resultado",
            title="Propuesta de aplicación del resultado",
            section="nota_3",
            note_ref="3",
            columns=_amount_cols(),
            rows=[
                _row("A reservas voluntarias", rdo_n, rdo_n1),
                _row("Total aplicación", rdo_n, rdo_n1, total=True),
            ],
            total_row_indices=[1],
        ),
        "t_inmovilizado_material": FinanceTable(
            id="t_inmovilizado_material",
            title="Inmovilizado material — valor neto contable",
            section="nota_5",
            note_ref="5",
            columns=_amount_cols(),
            rows=[
                _row("Inmovilizado material", imm_n, imm_n1),
                _row("Total", imm_n, imm_n1, total=True),
            ],
            total_row_indices=[1],
        ),
        "t_activos_financieros": FinanceTable(
            id="t_activos_financieros",
            title="Activos financieros — desglose principal",
            section="nota_6",
            note_ref="6",
            columns=_amount_cols(),
            rows=[
                _row("Inversiones financieras a largo plazo", cred_lp_n, cred_lp_n1),
                _row("Inversiones en empresas del grupo a corto plazo", grupo_cp_n, grupo_cp_n1),
                _row("Inversiones financieras a corto plazo", inv_cp_n, inv_cp_n1),
                _row(
                    "Total",
                    cred_lp_n + grupo_cp_n + inv_cp_n,
                    cred_lp_n1 + grupo_cp_n1 + inv_cp_n1,
                    total=True,
                ),
            ],
            total_row_indices=[3],
        ),
        "t_existencias": FinanceTable(
            id="t_existencias",
            title="Existencias",
            section="nota_7",
            note_ref="7",
            columns=_amount_cols(),
            rows=[
                _row("Existencias", exist_n, exist_n1),
                _row("Total", exist_n, exist_n1, total=True),
            ],
            total_row_indices=[1],
        ),
        "t_deudores_efectivo": FinanceTable(
            id="t_deudores_efectivo",
            title="Deudores comerciales y efectivo",
            section="nota_8",
            note_ref="8",
            columns=_amount_cols(),
            rows=[
                _row("Deudores comerciales y otras cuentas a cobrar", deud_n, deud_n1),
                _row("Efectivo y otros activos líquidos equivalentes", efec_n, efec_n1),
            ],
        ),
        "t_fondos_propios": FinanceTable(
            id="t_fondos_propios",
            title="Fondos propios",
            section="nota_9",
            note_ref="9",
            columns=_amount_cols(),
            rows=[
                _row("Capital escriturado", cap_n, cap_n1),
                _row("Reserva legal y estatutarias", legal_n, legal_n1),
                _row("Otras reservas", res_n, res_n1),
                _row("Otras aportaciones de socios", aport_n, aport_n1),
                _row("Resultado del ejercicio", rdo_n, rdo_n1),
                _row(
                    "Total fondos propios",
                    cap_n + legal_n + res_n + aport_n + rdo_n,
                    cap_n1 + legal_n1 + res_n1 + aport_n1 + rdo_n1,
                    total=True,
                ),
            ],
            total_row_indices=[5],
        ),
        "t_pasivos_financieros": FinanceTable(
            id="t_pasivos_financieros",
            title="Deudas y acreedores",
            section="nota_10",
            note_ref="10",
            columns=_amount_cols(),
            rows=[
                _row("Deudas a largo plazo", deudas_lp_n, deudas_lp_n1),
                _row("Deudas a corto plazo", deudas_cp_n, deudas_cp_n1),
                _row("Acreedores comerciales y otras cuentas a pagar", acree_n, acree_n1),
                _row(
                    "Total",
                    deudas_lp_n + deudas_cp_n + acree_n,
                    deudas_lp_n1 + deudas_cp_n1 + acree_n1,
                    total=True,
                ),
            ],
            total_row_indices=[3],
        ),
        "t_impuesto": FinanceTable(
            id="t_impuesto",
            title="Impuesto diferido",
            section="nota_11",
            note_ref="11",
            columns=_amount_cols(),
            rows=[
                _row("Activos por impuesto diferido", aid_n, aid_n1),
                _row("Pasivos por impuesto diferido", pid_n, pid_n1),
            ],
        ),
    }

    # Optional inmobiliarias table if material
    if abs(inv_imm_n) + abs(inv_imm_n1) > 0.5:
        tables["t_inversiones_inmobiliarias"] = FinanceTable(
            id="t_inversiones_inmobiliarias",
            title="Inversiones inmobiliarias — valor neto",
            section="nota_5b",
            note_ref="5",
            columns=_amount_cols(),
            rows=[
                _row("Inversiones inmobiliarias", inv_imm_n, inv_imm_n1),
                _row("Total", inv_imm_n, inv_imm_n1, total=True),
            ],
            total_row_indices=[1],
        )
    return tables


def _b(
    bid: str,
    kind: str,
    text: str,
    *,
    section: str,
    note_number: int | None = None,
    table_id: str | None = None,
    keep_with_next: bool = False,
    highlight: bool = False,
) -> ContentBlock:
    return ContentBlock(
        id=bid,
        kind=kind,  # type: ignore[arg-type]
        text=text,
        visible=True,
        section=section,
        note_number=note_number,
        table_id=table_id,
        keep_with_next=keep_with_next,
        highlight=highlight,
    )


def build_content(legal_name: str, nif: str, meta: dict, finance) -> ContentModel:
    rdo_n, rdo_n1 = _resultado(finance)
    has_imm = abs(sum(_find_balance(finance, "Inmovilizado Material"))) > 0.5 or abs(
        sum(_find_balance(finance, "Instal"))
    ) > 0.5
    has_inv_imm = False
    for ln in finance.statements.balance.lines:
        if "Inversiones inmobiliarias" in ln.label and (abs(ln.n) > 0.5 or abs(ln.n1) > 0.5):
            has_inv_imm = True
            break
    has_exist = False
    for ln in finance.statements.balance.lines:
        if "Existencias" in ln.label and (abs(ln.n) > 0.5 or abs(ln.n1) > 0.5):
            has_exist = True
            break

    blocks: list[ContentBlock] = [
        _b("cover.subtitle", "paragraph", "Cuentas Anuales", section="portada"),
        _b("h.nota_1", "heading1", "Actividad de la Sociedad", section="nota_1", note_number=1, keep_with_next=True),
        _b(
            "p.nota_1_1",
            "paragraph",
            (
                f"{legal_name} (en adelante, «la Sociedad»), con NIF {nif}, tiene su domicilio social "
                f"en Avenida de la Cañada, 46, Coslada (Madrid). La Sociedad {meta['activity']}"
            ),
            section="nota_1",
        ),
        _b(
            "p.nota_1_2",
            "paragraph",
            (
                "La Sociedad forma parte del Grupo Inmobiliaria Corral, en los términos del "
                "artículo 42 del Código de Comercio. La sociedad dominante del Grupo es "
                "Inmobiliaria Corral, S.L., que formula cuentas anuales consolidadas."
            ),
            section="nota_1",
        ),
        _b(
            "p.nota_1_3",
            "paragraph",
            (
                "La moneda funcional es el euro. El ejercicio social coincide con el año natural, "
                "cerrándose al 31 de diciembre."
            ),
            section="nota_1",
        ),
        _b("h.nota_2", "heading1", "Bases de presentación de las cuentas anuales", section="nota_2", note_number=2, keep_with_next=True),
        _b("h.nota_2_a", "heading2", "a) Imagen fiel", section="nota_2", keep_with_next=True),
        _b(
            "p.nota_2_a",
            "paragraph",
            (
                "Las cuentas anuales se han formulado a partir de los registros contables de la "
                "Sociedad al 31 de diciembre de 2025, de acuerdo con el Plan General de Contabilidad "
                "y el resto de normativa mercantil aplicable, de forma que muestran la imagen fiel "
                "del patrimonio, de la situación financiera y de los resultados."
            ),
            section="nota_2",
        ),
        _b("h.nota_2_b", "heading2", "b) Comparación de la información", section="nota_2", keep_with_next=True),
        _b(
            "p.nota_2_b",
            "paragraph",
            (
                "Se presentan, a efectos comparativos, las cifras del ejercicio terminado el "
                "31 de diciembre de 2024."
            ),
            section="nota_2",
        ),
        _b("h.nota_2_c", "heading2", "c) Empresa en funcionamiento", section="nota_2", keep_with_next=True),
        _b(
            "p.nota_2_c",
            "paragraph",
            (
                "Los Administradores han formulado estas cuentas anuales siguiendo el principio de "
                "empresa en funcionamiento."
            ),
            section="nota_2",
        ),
        _b("h.nota_3", "heading1", "Aplicación de resultados", section="nota_3", note_number=3, keep_with_next=True),
        _b(
            "p.nota_3_1",
            "paragraph",
            (
                f"El resultado del ejercicio 2025 asciende a {_amt(rdo_n)} euros "
                f"(2024: {_amt(rdo_n1)} euros). La propuesta de aplicación del resultado del "
                "ejercicio 2025, pendiente de aprobación por la Junta General de Socios, es la siguiente:"
            ),
            section="nota_3",
        ),
        _b("t.nota_3", "table_ref", "", section="nota_3", table_id="t_aplicacion_resultado"),
        _b(
            "p.nota_3_2",
            "paragraph",
            (
                "Se destinará a reserva legal el 10% del beneficio del ejercicio hasta alcanzar, "
                "al menos, el 20% del capital social, en la medida en que dicha reserva no se "
                "encuentre completamente dotada, conforme a la Ley de Sociedades de Capital."
            ),
            section="nota_3",
        ),
        _b("h.nota_4", "heading1", "Normas de registro y valoración", section="nota_4", note_number=4, keep_with_next=True),
        _b(
            "p.nota_4_intro",
            "paragraph",
            "Las principales normas de registro y valoración aplicadas son las siguientes:",
            section="nota_4",
        ),
        _b("h.nota_4_a", "heading2", "a) Inmovilizado material e inversiones inmobiliarias", section="nota_4", keep_with_next=True),
        _b(
            "p.nota_4_a",
            "paragraph",
            (
                "Se valoran a coste de adquisición o producción, minorado por la amortización "
                "acumulada y, en su caso, por las correcciones valorativas por deterioro."
            ),
            section="nota_4",
        ),
        _b("h.nota_4_b", "heading2", "b) Activos y pasivos financieros", section="nota_4", keep_with_next=True),
        _b(
            "p.nota_4_b",
            "paragraph",
            (
                "Se clasifican y valoran conforme al PGC según su naturaleza y el modelo de negocio. "
                "Con carácter general, los préstamos y partidas a cobrar/pagar se valoran a coste amortizado."
            ),
            section="nota_4",
        ),
        _b("h.nota_4_c", "heading2", "c) Existencias", section="nota_4", keep_with_next=True),
        _b(
            "p.nota_4_c",
            "paragraph",
            (
                "Se valoran al precio de adquisición o coste de producción, o a valor neto realizable "
                "si este fuese inferior."
            ),
            section="nota_4",
        ),
        _b("h.nota_4_d", "heading2", "d) Impuesto sobre beneficios", section="nota_4", keep_with_next=True),
        _b(
            "p.nota_4_d",
            "paragraph",
            (
                "El gasto o ingreso por impuesto comprende el impuesto corriente y el diferido. "
                "Los activos por impuesto diferido se reconocen cuando es probable su recuperación."
            ),
            section="nota_4",
        ),
        _b("h.nota_4_e", "heading2", "e) Ingresos y gastos", section="nota_4", keep_with_next=True),
        _b(
            "p.nota_4_e",
            "paragraph",
            "Se imputan según el criterio de devengo.",
            section="nota_4",
        ),
    ]

    note = 5
    if has_imm:
        blocks += [
            _b(f"h.nota_{note}", "heading1", "Inmovilizado material", section=f"nota_{note}", note_number=note, keep_with_next=True),
            _b(f"p.nota_{note}_1", "paragraph", "El detalle del inmovilizado material al cierre es el siguiente:", section=f"nota_{note}"),
            _b(f"t.nota_{note}", "table_ref", "", section=f"nota_{note}", table_id="t_inmovilizado_material"),
        ]
        note += 1
    if has_inv_imm:
        blocks += [
            _b(f"h.nota_{note}", "heading1", "Inversiones inmobiliarias", section=f"nota_{note}", note_number=note, keep_with_next=True),
            _b(f"p.nota_{note}_1", "paragraph", "El detalle de las inversiones inmobiliarias al cierre es el siguiente:", section=f"nota_{note}"),
            _b(f"t.nota_{note}", "table_ref", "", section=f"nota_{note}", table_id="t_inversiones_inmobiliarias"),
        ]
        note += 1

    blocks += [
        _b(f"h.nota_{note}", "heading1", "Activos financieros", section=f"nota_{note}", note_number=note, keep_with_next=True),
        _b(f"p.nota_{note}_1", "paragraph", "El desglose de los principales activos financieros es el siguiente:", section=f"nota_{note}"),
        _b(f"t.nota_{note}", "table_ref", "", section=f"nota_{note}", table_id="t_activos_financieros"),
    ]
    note += 1

    if has_exist:
        blocks += [
            _b(f"h.nota_{note}", "heading1", "Existencias", section=f"nota_{note}", note_number=note, keep_with_next=True),
            _b(f"p.nota_{note}_1", "paragraph", "La composición de las existencias al cierre es la siguiente:", section=f"nota_{note}"),
            _b(f"t.nota_{note}", "table_ref", "", section=f"nota_{note}", table_id="t_existencias"),
        ]
        note += 1

    blocks += [
        _b(f"h.nota_{note}", "heading1", "Deudores comerciales y efectivo", section=f"nota_{note}", note_number=note, keep_with_next=True),
        _b(f"p.nota_{note}_1", "paragraph", "El detalle de estos epígrafes al cierre es el siguiente:", section=f"nota_{note}"),
        _b(f"t.nota_{note}", "table_ref", "", section=f"nota_{note}", table_id="t_deudores_efectivo"),
    ]
    note += 1

    blocks += [
        _b(f"h.nota_{note}", "heading1", "Fondos propios", section=f"nota_{note}", note_number=note, keep_with_next=True),
        _b(f"p.nota_{note}_1", "paragraph", "La composición de los fondos propios es la siguiente:", section=f"nota_{note}"),
        _b(f"t.nota_{note}", "table_ref", "", section=f"nota_{note}", table_id="t_fondos_propios"),
    ]
    note += 1

    blocks += [
        _b(f"h.nota_{note}", "heading1", "Pasivos financieros", section=f"nota_{note}", note_number=note, keep_with_next=True),
        _b(f"p.nota_{note}_1", "paragraph", "El detalle de las deudas y acreedores al cierre es el siguiente:", section=f"nota_{note}"),
        _b(f"t.nota_{note}", "table_ref", "", section=f"nota_{note}", table_id="t_pasivos_financieros"),
    ]
    note += 1

    blocks += [
        _b(f"h.nota_{note}", "heading1", "Situación fiscal", section=f"nota_{note}", note_number=note, keep_with_next=True),
        _b(
            f"p.nota_{note}_1",
            "paragraph",
            "El detalle de los saldos por impuesto diferido es el siguiente:",
            section=f"nota_{note}",
        ),
        _b(f"t.nota_{note}", "table_ref", "", section=f"nota_{note}", table_id="t_impuesto"),
        _b(
            f"p.nota_{note}_pend",
            "paragraph",
            (
                f"SOLICITAR — Contraste fiscal fino ejercicio 2025: {meta['note_fiscal']} "
                "Hasta disponer de la liquidación/individual 2025 no se cierra el desglose de "
                "impuesto corriente ni la conciliación del gasto por IS."
            ),
            section=f"nota_{note}",
            highlight=True,
        ),
    ]
    note += 1

    blocks += [
        _b(f"h.nota_{note}", "heading1", "Ingresos y gastos", section=f"nota_{note}", note_number=note, keep_with_next=True),
        _b(
            f"p.nota_{note}_1",
            "paragraph",
            (
                "La cuenta de pérdidas y ganancias adjunta recoge el detalle de ingresos y gastos "
                f"del ejercicio. El resultado del ejercicio se informa en la nota de aplicación de resultados."
            ),
            section=f"nota_{note}",
        ),
    ]
    note += 1

    # Otra información — pendientes en amarillo
    blocks += [
        _b(f"h.nota_{note}", "heading1", "Otra información", section=f"nota_{note}", note_number=note, keep_with_next=True),
        _b(f"h.nota_{note}_a", "heading2", "a) Personal / plantilla media", section=f"nota_{note}", keep_with_next=True),
        _b(
            f"p.nota_{note}_a",
            "paragraph",
            (
                f"SOLICITAR — Plantilla media ejercicio 2025: {meta['note_plantilla_2024']} "
                "Se solicita el listado de promedio de plantilla del periodo 01/01/2025-31/12/2025."
            ),
            section=f"nota_{note}",
            highlight=True,
        ),
        _b(f"h.nota_{note}_b", "heading2", "b) Periodo medio de pago a proveedores", section=f"nota_{note}", keep_with_next=True),
        _b(
            f"p.nota_{note}_b",
            "paragraph",
            (
                f"SOLICITAR — PMP a proveedores ejercicio 2025: {meta['note_pmp_2024']} "
                "Se solicita el cálculo del periodo medio de pago (Ley 15/2010) del ejercicio 2025."
            ),
            section=f"nota_{note}",
            highlight=True,
        ),
        _b(f"h.nota_{note}_c", "heading2", "c) Hechos posteriores", section=f"nota_{note}", keep_with_next=True),
        _b(
            f"p.nota_{note}_c",
            "paragraph",
            (
                "Desde el 31 de diciembre de 2025 hasta la fecha de formulación, no se tiene "
                "constancia de hechos posteriores que impliquen ajuste a las cifras, sin perjuicio "
                "de la confirmación formal en carta de manifestaciones."
            ),
            section=f"nota_{note}",
        ),
    ]

    return ContentModel(blocks=blocks)


def rebuild_one(project_id: str) -> None:
    meta = ENTITIES[project_id]
    project = load_project(project_id)
    finance = load_finance(project_id)
    nif = NIFS.get(project_id) or meta["nif"]

    tables = build_tables(finance)
    # Drop empty optional inmobiliarias if not created
    finance.tables = tables
    content = build_content(project.entity.legal_name, nif, meta, finance)

    # Hide empty disclosure tables by removing table_ref if all zero? keep for transparency

    save_finance(project_id, finance)
    save_content(project_id, content)

    out_dir = ROOT / "clientes" / "INMOBILIARIA CORRAL, S.L" / "02_Trabajo_informes"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / meta["word"]
    export_docx(project, finance, content, out)
    res = validate_balance(finance)
    yellow = sum(1 for b in content.blocks if b.highlight)
    print(
        f"{meta['short']}: blocks={len(content.blocks)} tables={len(finance.tables)} "
        f"yellow={yellow} balance_ok={res.ok} -> {out.name}"
    )


def main() -> None:
    # Solicitudes pendientes — documento de control
    control = (
        ROOT
        / "clientes"
        / "INMOBILIARIA CORRAL, S.L"
        / "02_Trabajo_informes"
        / "SOLICITAR_info_pendiente_2025.txt"
    )
    control.parent.mkdir(parents=True, exist_ok=True)
    control.write_text(
        "\n".join(
            [
                "INFORMACIÓN A SOLICITAR (ejercicio 2025) — Grupo Corral / memorias pequeñas",
                "",
                "Revisado en: clientes/INMOBILIARIA CORRAL, S.L",
                "",
                "1) Plantilla media 01/01/2025-31/12/2025",
                "   - Hay PROMEDIO PLANTILLA 2024 (PGF y PBP entre otras).",
                "   - NO hay listado 2025. CCA y AUTOTYPE tampoco aparecen en ese Excel 2024.",
                "   => SOLICITAR listados 2025 de PGF, PBP, CCA y AUTOTYPE.",
                "",
                "2) Periodo medio de pago a proveedores (Ley 15/2010) ejercicio 2025",
                "   - Hay cálculo PMP 2024 de grupo (incluye PGFC/PBPC).",
                "   - NO hay cálculo 2025.",
                "   => SOLICITAR PMP 2025 por sociedad (o agregado con desglose).",
                "",
                "3) Contraste fiscal fino 2025",
                "   - Hay sábanas fiscales consolidación 2025 y Modelo 200 2024 (CCA, AUTOTYPE).",
                "   - Falta liquidación/individual 2025 y cuadre fino gasto IS vs PyG por sociedad.",
                "   => SOLICITAR liquidaciones IS 2025 / papeles de soporte individual.",
                "",
                "Estos tres puntos están resaltados en AMARILLO en las memorias del programa.",
            ]
        ),
        encoding="utf-8",
    )

    for pid in ENTITIES:
        rebuild_one(pid)
    print("Control:", control)


if __name__ == "__main__":
    main()
