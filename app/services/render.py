from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.domain.content import ContentModel
from app.domain.finance import FinanceModel
from app.domain.project import Project
from app.services.context_builder import build_context

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def render_report_html(
    project: Project,
    finance: FinanceModel,
    content: ContentModel,
    editable: bool = False,
) -> str:
    ctx = build_context(project, finance, content)
    ctx["editable"] = editable
    ctx["styles_css"] = (TEMPLATES_DIR / "report" / "styles.css").read_text(encoding="utf-8")
    ctx["layout_js"] = (STATIC_DIR / "report" / "layout.js").read_text(encoding="utf-8")
    ctx["editor_js"] = (STATIC_DIR / "report" / "editor.js").read_text(encoding="utf-8")
    ctx["table_editor_js"] = (STATIC_DIR / "report" / "table_editor.js").read_text(encoding="utf-8")
    template = _env().get_template("report/base.html")
    return template.render(**ctx)


def render_ui(template_name: str, **kwargs) -> str:
    template = _env().get_template(f"ui/{template_name}")
    return template.render(**kwargs)
