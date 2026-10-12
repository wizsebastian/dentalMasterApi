"""Guía interactiva: contratos de la vista pública `/guia` y del análisis."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ESTRICTO = ConfigDict(extra="forbid")

EstadoPaso = Literal["", "ok", "falla", "duda"]


class GuiaSesionCrear(BaseModel):
    model_config = ESTRICTO

    nombre: str = Field(min_length=2, max_length=120)
    rol: str | None = Field(default=None, max_length=60)


class GuiaPasoEscribir(BaseModel):
    model_config = ESTRICTO

    estado: EstadoPaso
    nota: str = Field(default="", max_length=4000)


class GuiaGeneralEscribir(BaseModel):
    model_config = ESTRICTO

    texto: str = Field(max_length=8000)


class GuiaRespuestaLeer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    paso_id: str
    estado: EstadoPaso
    nota: str
    actualizado_en: datetime


class GuiaSesionLeer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    nombre: str
    rol: str | None
    impresion_general: str
    creado_en: datetime
    actualizado_en: datetime
    respuestas: list[GuiaRespuestaLeer]


class GuiaSesionResumen(BaseModel):
    codigo: str
    nombre: str
    rol: str | None
    creado_en: datetime
    actualizado_en: datetime
    ok: int
    falla: int
    duda: int
    notas: int


class GuiaPasoResumen(BaseModel):
    """Un paso visto por todas las sesiones: dónde se atasca la gente."""

    paso_id: str
    ok: int
    falla: int
    duda: int


class GuiaResumen(BaseModel):
    sesiones: list[GuiaSesionResumen]
    pasos: list[GuiaPasoResumen]


class GuiaEventoLeer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    paso_id: str
    estado: str
    nota: str
    creado_en: datetime


class GuiaSesionExportada(GuiaSesionLeer):
    eventos: list[GuiaEventoLeer]
