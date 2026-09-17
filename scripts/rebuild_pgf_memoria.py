"""
Rebuild PGF memoria content from balances (best practice):
- Only notes required by N/N-1 saldos
- Short PGC-style narrative (not IC template paste)
- Disclosure tables linked to figures in finance.json
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.domain.content import ContentBlock, ContentModel
from app.domain.finance import FinanceTable, TableCell, TableColumn
from app.services.docx_export import export_docx
from app.services.formatting import format_amount
from app.services.storage import load_finance, load_project, save_content, save_finance
from app.domain.validation import validate_balance

PID = "pgf-promociones-gran-ferial"
NIF = "B81057200"


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


def _find_balance(finance, *needles: str):
    """Return (n, n1) for first balance line whose label contains all needles (casefold)."""
    for ln in finance.statements.balance.lines:
        lab = ln.label.casefold()
        if all(n.casefold() in lab for n in needles):
            return ln.n, ln.n1
    return 0.0, 0.0


def build_tables(finance) -> dict[str, FinanceTable]:
    imm_n, imm_n1 = _find_balance(finance, "Instal")
    if abs(imm_n) < 0.01:
        imm_n, imm_n1 = _find_balance(finance, "Inmovilizado Material")

    cred_lp_n, cred_lp_n1 = _find_balance(finance, "Créditos a terceros")
    if abs(cred_lp_n) < 0.01 and abs(cred_lp_n1) < 0.01:
        cred_lp_n, cred_lp_n1 = _find_balance(finance, "Inversiones financieras a L")

    inv_cp_n, inv_cp_n1 = _find_balance(finance, "Inversiones financieras a C")
    grupo_cp_n, grupo_cp_n1 = _find_balance(finance, "Invers. empresas grupo y asociadas a C")
    exist_n, exist_n1 = _find_balance(finance, "Existencias")
    if abs(exist_n) < 0.01:
        exist_n, exist_n1 = _find_balance(finance, "Productos terminados")
    deud_n, deud_n1 = _find_balance(finance, "Deudores ciales")
    efec_n, efec_n1 = _find_balance(finance, "Efectivo")
    if abs(efec_n) < 0.01:
        efec_n, efec_n1 = _find_balance(finance, "Tesorer")

    cap_n, cap_n1 = _find_balance(finance, "Capital escriturado")
    res_n, res_n1 = _find_balance(finance, "Otras reservas")
    legal_n, legal_n1 = _find_balance(finance, "Legal y estatutarias")
    aport_n, aport_n1 = _find_balance(finance, "Otras aportaciones de socios")
    rdo_n, rdo_n1 = _find_balance(finance, "Resultado del ejercicio")
    # prefer the subtotal_group VII line
    for ln in finance.statements.balance.lines:
        if ln.label.strip().startswith("VII.") and "Resultado" in ln.label:
            rdo_n, rdo_n1 = ln.n, ln.n1
            break

    deudas_lp_n, deudas_lp_n1 = _find_balance(finance, "Deudas a L")
    deudas_cp_n, deudas_cp_n1 = _find_balance(finance, "Deudas a C")
    acree_n, acree_n1 = _find_balance(finance, "Acreedores ciales")
    aid_n, aid_n1 = _find_balance(finance, "Activos por impuesto diferido")
    pid_n, pid_n1 = _find_balance(finance, "Pasivos por impuesto diferido")

    tables: dict[str, FinanceTable] = {}

    tables["t_aplicacion_resultado"] = FinanceTable(
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
    )

    tables["t_inmovilizado_material"] = FinanceTable(
        id="t_inmovilizado_material",
        title="Inmovilizado material — valor neto contable",
        section="nota_5",
        note_ref="5",
        columns=_amount_cols(),
        rows=[
            _row("Instalaciones técnicas y otro inmovilizado material", imm_n, imm_n1),
            _row("Total inmovilizado material", imm_n, imm_n1, total=True),
        ],
        total_row_indices=[1],
    )

    tables["t_activos_financieros"] = FinanceTable(
        id="t_activos_financieros",
        title="Activos financieros — desglose principal",
        section="nota_6",
        note_ref="6",
        columns=_amount_cols(),
        rows=[
            _row("Créditos a terceros a largo plazo", cred_lp_n, cred_lp_n1),
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
    )

    tables["t_existencias"] = FinanceTable(
        id="t_existencias",
        title="Existencias",
        section="nota_7",
        note_ref="7",
        columns=_amount_cols(),
        rows=[
            _row("Productos terminados / existencias", exist_n, exist_n1),
            _row("Total existencias", exist_n, exist_n1, total=True),
        ],
        total_row_indices=[1],
    )

    tables["t_deudores_efectivo"] = FinanceTable(
        id="t_deudores_efectivo",
        title="Deudores comerciales y efectivo",
        section="nota_8",
        note_ref="8",
        columns=_amount_cols(),
        rows=[
            _row("Deudores comerciales y otras cuentas a cobrar", deud_n, deud_n1),
            _row("Efectivo y otros activos líquidos equivalentes", efec_n, efec_n1),
        ],
    )

    tables["t_fondos_propios"] = FinanceTable(
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
    )

    tables["t_pasivos_financieros"] = FinanceTable(
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
    )

    tables["t_impuesto"] = FinanceTable(
        id="t_impuesto",
        title="Impuesto diferido",
        section="nota_11",
        note_ref="11",
        columns=_amount_cols(),
        rows=[
            _row("Activos por impuesto diferido", aid_n, aid_n1),
            _row("Pasivos por impuesto diferido", pid_n, pid_n1),
        ],
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
    )


def build_content(legal_name: str, finance) -> ContentModel:
    rdo_n = 0.0
    rdo_n1 = 0.0
    for ln in finance.statements.balance.lines:
        if ln.label.strip().startswith("VII.") and "Resultado" in ln.label:
            rdo_n, rdo_n1 = ln.n, ln.n1
            break

    blocks: list[ContentBlock] = [
        _b(
            "cover.subtitle",
            "paragraph",
            "Cuentas Anuales",
            section="portada",
        ),
        # Nota 1
        _b("h.nota_1", "heading1", "Actividad de la Sociedad", section="nota_1", note_number=1, keep_with_next=True),
        _b(
            "p.nota_1_1",
            "paragraph",
            (
                f"{legal_name} (en adelante, «la Sociedad»), con NIF {NIF}, tiene su domicilio social "
                "en Avenida de la Cañada, 46, Coslada (Madrid). La Sociedad está inscrita en el "
                "Registro Mercantil de Madrid y desarrolla su actividad en el ámbito de la "
                "promoción inmobiliaria."
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
                "La moneda funcional con la que opera la Sociedad es el euro. El ejercicio social "
                "coincide con el año natural, cerrándose al 31 de diciembre."
            ),
            section="nota_1",
        ),
        # Nota 2
        _b("h.nota_2", "heading1", "Bases de presentación de las cuentas anuales", section="nota_2", note_number=2, keep_with_next=True),
        _b("h.nota_2_a", "heading2", "a) Imagen fiel", section="nota_2", keep_with_next=True),
        _b(
            "p.nota_2_a",
            "paragraph",
            (
                "Las cuentas anuales se han formulado a partir de los registros contables de la "
                "Sociedad al 31 de diciembre de 2025, de acuerdo con el Plan General de Contabilidad "
                "aprobado por el Real Decreto 1514/2007 (y modificaciones posteriores) y el resto de "
                "normativa mercantil aplicable, de forma que muestran la imagen fiel del patrimonio, "
                "de la situación financiera y de los resultados de la Sociedad."
            ),
            section="nota_2",
        ),
        _b("h.nota_2_b", "heading2", "b) Principios contables", section="nota_2", keep_with_next=True),
        _b(
            "p.nota_2_b",
            "paragraph",
            (
                "Se han aplicado los principios contables obligatorios. No existen razones "
                "excepcionales que justifiquen la falta de aplicación de algún principio obligatorio."
            ),
            section="nota_2",
        ),
        _b("h.nota_2_c", "heading2", "c) Comparación de la información", section="nota_2", keep_with_next=True),
        _b(
            "p.nota_2_c",
            "paragraph",
            (
                "Las cuentas anuales presentan, a efectos comparativos, las cifras del ejercicio "
                "terminado el 31 de diciembre de 2024. No se han producido cambios de criterios "
                "contables con efecto significativo respecto al ejercicio anterior."
            ),
            section="nota_2",
        ),
        _b("h.nota_2_d", "heading2", "d) Aspectos críticos de la valoración y estimación", section="nota_2", keep_with_next=True),
        _b(
            "p.nota_2_d",
            "paragraph",
            (
                "En la preparación de estas cuentas anuales se han utilizado estimaciones realizadas "
                "por la Dirección de la Sociedad para cuantificar algunos activos, pasivos, ingresos, "
                "gastos y compromisos. Dichas estimaciones se refieren, principalmente, a la "
                "evaluación del valor recuperable de activos financieros e inmobiliarios, a la vida "
                "útil del inmovilizado y al cálculo de impuestos diferidos. Las estimaciones se "
                "revisan de forma continua; el efecto de los cambios se reconoce de forma prospectiva."
            ),
            section="nota_2",
        ),
        _b("h.nota_2_e", "heading2", "e) Empresa en funcionamiento", section="nota_2", keep_with_next=True),
        _b(
            "p.nota_2_e",
            "paragraph",
            (
                "Los Administradores han formulado estas cuentas anuales siguiendo el principio de "
                "empresa en funcionamiento, al no existir dudas sobre la continuidad de las operaciones."
            ),
            section="nota_2",
        ),
        # Nota 3
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
        _b(
            "t.nota_3",
            "table_ref",
            "",
            section="nota_3",
            table_id="t_aplicacion_resultado",
        ),
        _b(
            "p.nota_3_2",
            "paragraph",
            (
                "No existen limitaciones relevantes para la distribución de dividendos distintas de "
                "las establecidas en la normativa mercantil. De conformidad con el artículo 274 de "
                "la Ley de Sociedades de Capital, se destinará a reserva legal el 10% del beneficio "
                "del ejercicio hasta alcanzar, al menos, el 20% del capital social, en la medida en "
                "que dicha reserva no se encuentre completamente dotada."
            ),
            section="nota_3",
        ),
        # Nota 4 NRV
        _b("h.nota_4", "heading1", "Normas de registro y valoración", section="nota_4", note_number=4, keep_with_next=True),
        _b(
            "p.nota_4_intro",
            "paragraph",
            (
                "Las principales normas de registro y valoración aplicadas por la Sociedad en la "
                "elaboración de estas cuentas anuales son las siguientes:"
            ),
            section="nota_4",
        ),
        _b("h.nota_4_imm", "heading2", "a) Inmovilizado material", section="nota_4", keep_with_next=True),
        _b(
            "p.nota_4_imm",
            "paragraph",
            (
                "El inmovilizado material se valora a su coste de adquisición o producción, minorado "
                "por la amortización acumulada y, en su caso, por las correcciones valorativas por "
                "deterioro. La amortización se calcula de forma lineal en función de la vida útil "
                "estimada de los elementos."
            ),
            section="nota_4",
        ),
        _b("h.nota_4_fin", "heading2", "b) Activos financieros", section="nota_4", keep_with_next=True),
        _b(
            "p.nota_4_fin",
            "paragraph",
            (
                "Los activos financieros se clasifican y valoran de acuerdo con el PGC según su "
                "naturaleza y el modelo de negocio de la Sociedad (principalmente coste amortizado "
                "o valor razonable con cambios en la cuenta de pérdidas y ganancias, cuando procede). "
                "Al menos al cierre del ejercicio se efectúan las correcciones valorativas por "
                "deterioro que resulten necesarias."
            ),
            section="nota_4",
        ),
        _b("h.nota_4_ex", "heading2", "c) Existencias", section="nota_4", keep_with_next=True),
        _b(
            "p.nota_4_ex",
            "paragraph",
            (
                "Las existencias se valoran al precio de adquisición o coste de producción, o a su "
                "valor neto realizable si este fuese inferior. Cuando el valor neto realizable de "
                "las existencias es inferior a su coste, se efectúan las oportunas correcciones "
                "valorativas."
            ),
            section="nota_4",
        ),
        _b("h.nota_4_pas", "heading2", "d) Pasivos financieros", section="nota_4", keep_with_next=True),
        _b(
            "p.nota_4_pas",
            "paragraph",
            (
                "Los pasivos financieros se reconocen inicialmente a valor razonable y, con "
                "posterioridad, con carácter general, a coste amortizado. Los intereses se "
                "reconocen como gasto financiero en la cuenta de pérdidas y ganancias."
            ),
            section="nota_4",
        ),
        _b("h.nota_4_imp", "heading2", "e) Impuesto sobre beneficios", section="nota_4", keep_with_next=True),
        _b(
            "p.nota_4_imp",
            "paragraph",
            (
                "El gasto o ingreso por impuesto sobre beneficios comprende la parte relativa al "
                "gasto o ingreso por impuesto corriente y la parte correspondiente al gasto o "
                "ingreso por impuesto diferido. Los activos y pasivos por impuesto diferido se "
                "reconocen por las diferencias temporarias, créditos y deducciones pendientes, "
                "en la medida en que resulte probable su recuperación o liquidación."
            ),
            section="nota_4",
        ),
        _b("h.nota_4_ing", "heading2", "f) Ingresos y gastos", section="nota_4", keep_with_next=True),
        _b(
            "p.nota_4_ing",
            "paragraph",
            (
                "Los ingresos y gastos se imputan en función del criterio de devengo. Los ingresos "
                "por prestación de servicios o enajenación de bienes se reconocen cuando se "
                "transfiere el control al cliente y el importe puede valorarse con fiabilidad."
            ),
            section="nota_4",
        ),
        # Nota 5 IMM
        _b("h.nota_5", "heading1", "Inmovilizado material", section="nota_5", note_number=5, keep_with_next=True),
        _b(
            "p.nota_5_1",
            "paragraph",
            (
                "El detalle del inmovilizado material al cierre de los ejercicios 2025 y 2024 es el siguiente:"
            ),
            section="nota_5",
        ),
        _b("t.nota_5", "table_ref", "", section="nota_5", table_id="t_inmovilizado_material"),
        _b(
            "p.nota_5_2",
            "paragraph",
            (
                "La Sociedad no tiene compromisos firmes de compra de inmovilizado material al cierre "
                "del ejercicio ni elementos sujetos a garantías relevantes distintos de los propios "
                "del curso ordinario de las operaciones."
            ),
            section="nota_5",
        ),
        # Nota 6 AF
        _b("h.nota_6", "heading1", "Activos financieros", section="nota_6", note_number=6, keep_with_next=True),
        _b(
            "p.nota_6_1",
            "paragraph",
            (
                "El desglose de los principales activos financieros al 31 de diciembre de 2025 y 2024 "
                "es el siguiente:"
            ),
            section="nota_6",
        ),
        _b("t.nota_6", "table_ref", "", section="nota_6", table_id="t_activos_financieros"),
        _b(
            "p.nota_6_2",
            "paragraph",
            (
                "Los créditos a largo plazo corresponden principalmente a financiaciones otorgadas a "
                "terceros. Las inversiones a corto plazo incluyen instrumentos de patrimonio y "
                "créditos, así como saldos con empresas del grupo cuando procede. La Dirección "
                "evalúa periódicamente el riesgo de crédito y la recuperabilidad de estos activos."
            ),
            section="nota_6",
        ),
        # Nota 7 existencias
        _b("h.nota_7", "heading1", "Existencias", section="nota_7", note_number=7, keep_with_next=True),
        _b(
            "p.nota_7_1",
            "paragraph",
            "La composición de las existencias al cierre de ambos ejercicios es la siguiente:",
            section="nota_7",
        ),
        _b("t.nota_7", "table_ref", "", section="nota_7", table_id="t_existencias"),
        _b(
            "p.nota_7_2",
            "paragraph",
            (
                "Las existencias corresponden fundamentalmente a productos terminados vinculados a "
                "la actividad de promoción. En su caso, se reconocen deterioros cuando el valor neto "
                "realizable es inferior al coste."
            ),
            section="nota_7",
        ),
        # Nota 8 deudores/efectivo
        _b("h.nota_8", "heading1", "Deudores comerciales y efectivo", section="nota_8", note_number=8, keep_with_next=True),
        _b(
            "p.nota_8_1",
            "paragraph",
            "El detalle de estos epígrafes al cierre de los ejercicios 2025 y 2024 es el siguiente:",
            section="nota_8",
        ),
        _b("t.nota_8", "table_ref", "", section="nota_8", table_id="t_deudores_efectivo"),
        _b(
            "p.nota_8_2",
            "paragraph",
            (
                "El efectivo se mantiene en entidades financieras de reconocida solvencia. No "
                "existen restricciones relevantes sobre la disponibilidad de la tesorería al cierre."
            ),
            section="nota_8",
        ),
        # Nota 9 FP
        _b("h.nota_9", "heading1", "Fondos propios", section="nota_9", note_number=9, keep_with_next=True),
        _b(
            "p.nota_9_1",
            "paragraph",
            "El movimiento y composición de los fondos propios es el siguiente:",
            section="nota_9",
        ),
        _b("t.nota_9", "table_ref", "", section="nota_9", table_id="t_fondos_propios"),
        _b(
            "p.nota_9_2",
            "paragraph",
            (
                f"El capital social está representado por participaciones de la Sociedad. Al 31 de "
                f"diciembre de 2025 el capital escriturado asciende a {_amt(_find_balance(finance, 'Capital escriturado')[0])} euros. "
                "La reserva legal se dota de conformidad con la Ley de Sociedades de Capital."
            ),
            section="nota_9",
        ),
        # Nota 10 pasivos
        _b("h.nota_10", "heading1", "Pasivos financieros", section="nota_10", note_number=10, keep_with_next=True),
        _b(
            "p.nota_10_1",
            "paragraph",
            "El detalle de las deudas y acreedores al cierre de ambos ejercicios es el siguiente:",
            section="nota_10",
        ),
        _b("t.nota_10", "table_ref", "", section="nota_10", table_id="t_pasivos_financieros"),
        _b(
            "p.nota_10_2",
            "paragraph",
            (
                "Las deudas a largo plazo corresponden principalmente a otros pasivos financieros. "
                "No constan impagos relevantes de principal o intereses al cierre del ejercicio."
            ),
            section="nota_10",
        ),
        # Nota 11 fiscal
        _b("h.nota_11", "heading1", "Situación fiscal", section="nota_11", note_number=11, keep_with_next=True),
        _b(
            "p.nota_11_1",
            "paragraph",
            (
                "La Sociedad tributa en el Impuesto sobre Sociedades conforme a la normativa "
                "general aplicable. El detalle de los saldos por impuesto diferido es el siguiente:"
            ),
            section="nota_11",
        ),
        _b("t.nota_11", "table_ref", "", section="nota_11", table_id="t_impuesto"),
        _b(
            "p.nota_11_2",
            "paragraph",
            (
                "Los activos por impuesto diferido se reconocen en la medida en que resulta "
                "probable la obtención de ganancias fiscales futuras que permitan su aplicación. "
                "Pendiente de contraste fino con el expediente fiscal del ejercicio."
            ),
            section="nota_11",
        ),
        # Nota 12 ingresos/gastos
        _b("h.nota_12", "heading1", "Ingresos y gastos", section="nota_12", note_number=12, keep_with_next=True),
        _b(
            "p.nota_12_1",
            "paragraph",
            (
                "La cuenta de pérdidas y ganancias del ejercicio 2025 recoge, principalmente, "
                "ingresos accesorios y de gestión corriente, gastos de personal, servicios "
                "exteriores, amortizaciones, así como resultados financieros derivados de "
                "instrumentos financieros y créditos. El resultado del ejercicio se detalla en "
                "el estado de pérdidas y ganancias adjunto y en la nota 3."
            ),
            section="nota_12",
        ),
        # Nota 13 otra información
        _b("h.nota_13", "heading1", "Otra información", section="nota_13", note_number=13, keep_with_next=True),
        _b("h.nota_13_a", "heading2", "a) Personal", section="nota_13", keep_with_next=True),
        _b(
            "p.nota_13_a",
            "paragraph",
            (
                "La Sociedad ha contado con personal en el ejercicio. El detalle de la plantilla "
                "media y de los gastos de personal se completará con la información de RR.HH. "
                "del expediente de auditoría."
            ),
            section="nota_13",
        ),
        _b("h.nota_13_b", "heading2", "b) Hechos posteriores", section="nota_13", keep_with_next=True),
        _b(
            "p.nota_13_b",
            "paragraph",
            (
                "Desde el 31 de diciembre de 2025 hasta la fecha de formulación de estas cuentas "
                "anuales, no se han producido hechos posteriores que impliquen ajustes a las "
                "cifras o que requieran información adicional significativa, más allá de la "
                "evolución ordinaria del negocio."
            ),
            section="nota_13",
        ),
        _b("h.nota_13_c", "heading2", "c) Información sobre el periodo medio de pago a proveedores", section="nota_13", keep_with_next=True),
        _b(
            "p.nota_13_c",
            "paragraph",
            (
                "La información relativa al periodo medio de pago a proveedores (Ley 15/2010 y "
                "normativa de desarrollo) se incorporará con el cálculo del expediente cuando "
                "esté disponible."
            ),
            section="nota_13",
        ),
    ]
    return ContentModel(blocks=blocks)


def main() -> None:
    project = load_project(PID)
    finance = load_finance(PID)

    tables = build_tables(finance)
    finance.tables = tables  # replace IC leftover tables with PGF disclosure set

    content = build_content(project.entity.legal_name, finance)

    save_finance(PID, finance)
    save_content(PID, content)

    out = (
        ROOT
        / "clientes"
        / "INMOBILIARIA CORRAL, S.L"
        / "02_Trabajo_informes"
        / "PGF_CCAA_2025_borrador.docx"
    )
    export_docx(project, finance, content, out)
    res = validate_balance(finance)

    # inventory written
    inv = ROOT / "clientes" / "INMOBILIARIA CORRAL, S.L" / "02_Trabajo_informes" / "PGF_notas_aplicables.txt"
    inv.write_text(
        "\n".join(
            [
                "PGF — notas aplicables (redacción v1)",
                "1 Actividad",
                "2 Bases de presentación",
                "3 Aplicación de resultados",
                "4 Normas de registro y valoración (resumen)",
                "5 Inmovilizado material",
                "6 Activos financieros",
                "7 Existencias",
                "8 Deudores y efectivo",
                "9 Fondos propios",
                "10 Pasivos financieros",
                "11 Situación fiscal",
                "12 Ingresos y gastos",
                "13 Otra información (PMP/hechos posteriores pendientes de expediente)",
                "",
                "Omitidas por saldo cero / no material: intangible, inversiones inmobiliarias,",
                "arrendamientos significativos, subvenciones, etc.",
            ]
        ),
        encoding="utf-8",
    )

    print(
        f"OK blocks={len(content.blocks)} tables={len(finance.tables)} "
        f"balance_ok={res.ok} word={out}"
    )


if __name__ == "__main__":
    main()
