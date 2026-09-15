from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.domain.content import ContentModel
from app.domain.finance import FinanceModel
from app.domain.project import Project
from app.services.context_builder import build_context

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def render_report_html(project: Project, finance: FinanceModel, content: ContentModel) -> str:
    ctx = build_context(project, finance, content)
    styles_path = TEMPLATES_DIR / "report" / "styles.css"
    ctx["styles_css"] = styles_path.read_text(encoding="utf-8")
    template = _env().get_template("report/base.html")
    return template.render(**ctx)


def render_ui(template_name: str, **kwargs) -> str:
    template = _env().get_template(f"ui/{template_name}")
    return template.render(**kwargs)
