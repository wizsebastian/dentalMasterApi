"""Schemas de archivos del expediente."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ORM = ConfigDict(from_attributes=True)

TipoArchivo = Literal["foto", "radiografia_periapical", "panoramica", "cbct", "laboratorio", "otro"]


class ArchivoLeer(BaseModel):
    model_config = ORM

    id: int
    nombre_original: str
    mime: str
    bytes: int
    creado_en: datetime


class ArchivoClinicoLeer(BaseModel):
    model_config = ORM

    id: int
    paciente_id: int
    consulta_id: int | None
    tipo: str
    codigo_fdi: int | None
    titulo: str | None
    archivo: ArchivoLeer | None
    url: str | None = Field(description="Referencia externa, cuando no hay archivo en el almacén")
    tomado_en: date | None
    creado_en: datetime


class ArchivoClinicoActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: TipoArchivo | None = None
    titulo: str | None = Field(default=None, max_length=160)
    codigo_fdi: int | None = None
    tomado_en: date | None = None
