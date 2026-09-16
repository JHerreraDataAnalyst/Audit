"""Visual layout fixtures: mutate content/finance then the shared layout engine reflows."""

from __future__ import annotations

from copy import deepcopy

from app.domain.content import ContentBlock, ContentModel
from app.domain.finance import FinanceModel

LONG_PARAGRAPH = (
    "Los resultados de las distintas categorías de activos financieros se presentan "
    "comparados con el ejercicio anterior, incluyendo un desglose pormenorizado de "
    "la evolución de las inversiones, los deudores comerciales y la tesorería. "
) * 18

SHORT_PARAGRAPH = "El importe neto de la cifra de negocios se presenta comparativamente."

NARRATIVE_IDS = [
    "intro.body",
    "narrative.a",
    "narrative.b",
    "narrative.c",
    "narrative.d",
    "narrative.e",
    "narrative.f",
    "narrative.g",
    "narrative.h",
    "narrative.i",
    "narrative.j",
]


CASES = [
    {
        "id": "1",
        "title": "Párrafo corto",
        "detail": "Un párrafo de una línea; el resto del flujo se compacta.",
    },
    {
        "id": "2",
        "title": "Párrafo extremadamente largo",
        "detail": "Un bloque que no cabe en una página; el documento continúa sin solaparse.",
    },
    {
        "id": "3",
        "title": "Eliminar un párrafo",
        "detail": "Se elimina narrative.h; el hueco se cierra y el contenido posterior sube.",
    },
    {
        "id": "4",
        "title": "Eliminar varios consecutivos",
        "detail": "Se eliminan H, I y J; la página 1 aprovecha el espacio libre.",
    },
    {
        "id": "5",
        "title": "Agregar un párrafo",
        "detail": "Se inserta un párrafo nuevo tras intro.body.",
    },
    {
        "id": "6",
        "title": "Agregar líneas a un párrafo",
        "detail": "intro.body pasa de corto a varias líneas; empuja el contenido posterior.",
    },
    {
        "id": "7",
        "title": "Compactar hacia la página anterior",
        "detail": "Se reduce narrativa para que el Balance pueda empezar antes.",
    },
    {
        "id": "8",
        "title": "Forzar salto de página",
        "detail": "Se alarga la narrativa para que el Balance pase a la página siguiente.",
    },
    {
        "id": "9",
        "title": "Cambiar el tamaño de una tabla",
        "detail": "Se dejan solo totales del Activo; la tabla ocupa menos y refluja.",
    },
    {
        "id": "10",
        "title": "Agregar filas a una tabla",
        "detail": "Se duplican partidas de detalle; si no cabe, la tabla pasa o se parte con encabezado.",
    },
]


def apply_case(case_id: str, content: ContentModel, finance: FinanceModel) -> tuple[ContentModel, FinanceModel]:
    content = ContentModel.model_validate(content.model_dump())
    finance = FinanceModel.model_validate(finance.model_dump())
    cid = str(case_id)

    if cid == "1":
        _set_text(content, "intro.body", SHORT_PARAGRAPH)
    elif cid == "2":
        _set_text(content, "intro.body", LONG_PARAGRAPH)
    elif cid == "3":
        content.delete("narrative.h")
    elif cid == "4":
        for bid in ("narrative.h", "narrative.i", "narrative.j"):
            content.delete(bid)
    elif cid == "5":
        content.insert_after(
            "intro.body",
            ContentBlock(
                id="narrative.inserted",
                kind="paragraph",
                text="Párrafo insertado en la prueba 5: describe un hecho posterior al cierre sin alterar el resto de la estructura.",
            ),
        )
    elif cid == "6":
        intro = content.get("intro.body")
        extra = (
            " Adicionalmente, la Sociedad informa de la evolución de las categorías "
            "de activos financieros, de los saldos con empresas del grupo y de la "
            "tesorería al cierre, con el detalle necesario para la lectura del Balance."
        )
        if intro:
            intro.text = intro.text + extra + extra
    elif cid == "7":
        for bid in NARRATIVE_IDS[1:]:
            content.delete(bid)
        _set_text(content, "intro.body", SHORT_PARAGRAPH)
    elif cid == "8":
        for bid in NARRATIVE_IDS:
            _set_text(content, bid, LONG_PARAGRAPH[:900] if content.get(bid) else LONG_PARAGRAPH[:900])
    elif cid == "9":
        lines = finance.statements.balance.lines
        finance.statements.balance.lines = [
            ln for ln in lines if ln.role in ("total", "subtotal") or ln.section == "equity_liability"
        ]
    elif cid == "10":
        extras = []
        for ln in list(finance.statements.balance.lines):
            if ln.section == "asset" and ln.role == "detail":
                clone = deepcopy(ln)
                clone.id = f"{ln.id}_extra"
                clone.label = f"{ln.label} (ampliación)"
                extras.append((ln.id, clone))
        lines = list(finance.statements.balance.lines)
        for src_id, clone in reversed(extras):
            for i, ln in enumerate(lines):
                if ln.id == src_id:
                    lines.insert(i + 1, clone)
                    break
        finance.statements.balance.lines = lines
    else:
        raise ValueError(f"Caso de layout desconocido: {case_id}")

    return content, finance


def _set_text(content: ContentModel, block_id: str, text: str) -> None:
    block = content.get(block_id)
    if block:
        block.text = text
    else:
        content.upsert(ContentBlock(id=block_id, kind="paragraph", text=text))
