from __future__ import annotations

import json
from pathlib import Path

from app.domain.content import ContentModel
from app.domain.finance import FinanceModel
from app.domain.project import Project

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "projects"
OUTPUTS_DIR = ROOT / "outputs"
REFERENCE_DIR = ROOT / "reference"


def project_dir(project_id: str) -> Path:
    return DATA_DIR / project_id


def list_projects() -> list[str]:
    if not DATA_DIR.exists():
        return []
    return sorted(
        p.name for p in DATA_DIR.iterdir() if p.is_dir() and (p / "project.json").exists()
    )


def load_project(project_id: str) -> Project:
    path = project_dir(project_id) / "project.json"
    return Project.model_validate_json(path.read_text(encoding="utf-8"))


def load_finance(project_id: str) -> FinanceModel:
    path = project_dir(project_id) / "finance.json"
    return FinanceModel.model_validate_json(path.read_text(encoding="utf-8"))


def load_content(project_id: str) -> ContentModel:
    path = project_dir(project_id) / "content.json"
    return ContentModel.model_validate_json(path.read_text(encoding="utf-8"))


def save_finance(project_id: str, finance: FinanceModel) -> None:
    path = project_dir(project_id) / "finance.json"
    path.write_text(
        json.dumps(finance.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_content(project_id: str, content: ContentModel) -> None:
    path = project_dir(project_id) / "content.json"
    path.write_text(
        json.dumps(content.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_project(project: Project) -> None:
    path = project_dir(project.id) / "project.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(project.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
