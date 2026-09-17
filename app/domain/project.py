from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class Entity(BaseModel):
    legal_name: str
    legal_form_note: str = ""


class Period(BaseModel):
    current_end: date
    prior_end: date
    currency: str = "EUR"
    currency_label: str = "Euros"


class Project(BaseModel):
    id: str
    entity: Entity
    period: Period
    report_type: str = "ccaa_mvp"
    title: str = "Cuentas Anuales"
    client_group: str = ""  # p.ej. "Grupo Inmobiliaria Corral" — agrupa en el dashboard

