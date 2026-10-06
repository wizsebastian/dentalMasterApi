"""Schemas de implantes y su seguimiento."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import EstadoImplante

ORM = ConfigDict(from_attributes=True)
ESTRICTO = ConfigDict(extra="forbid")

TipoEvento = Literal["colocacion", "segunda_fase", "control", "carga", "complicacion", "retiro"]
Milimetros = Field(default=None, gt=0, lt=30, max_digits=3, decimal_places=1)


class SistemaLeer(BaseModel):
    model_config = ORM

    id: int
    marca: str
    linea: str
    conexion: str | None
    proveedor: str | None
    activo: bool


class SistemaCrear(BaseModel):
    model_config = ESTRICTO

    marca: str = Field(min_length=1, max_length=80)
    linea: str = Field(min_length=1, max_length=80)
    conexion: str | None = Field(default=None, max_length=80)
    proveedor: str | None = Field(default=None, max_length=120)


class EventoLeer(BaseModel):
    model_config = ORM

    id: int
    fecha: date
    tipo: str
    doctor_id: int | None
    isq: int | None
    hallazgos: str | None
    notas: str | None


class EventoCrear(BaseModel):
    """Un hito del seguimiento. Algunos mueven el estado del implante solos:
    «carga» lo deja cargado y fecha la carga; «retiro», explantado."""

    model_config = ESTRICTO

    tipo: TipoEvento
    fecha: date | None = Field(default=None, description="Por defecto, hoy")
    doctor_id: int | None = None
    isq: int | None = Field(default=None, ge=1, le=100)
    hallazgos: str | None = None
    notas: str | None = None
    estado: EstadoImplante | None = Field(
        default=None, description="Estado en que queda el implante tras el evento"
    )


class ImplanteCampos(BaseModel):
    referencia: str | None = Field(default=None, max_length=80)
    serie: str | None = Field(default=None, max_length=80)
    diametro_mm: Decimal | None = Milimetros
    longitud_mm: Decimal | None = Milimetros
    plataforma: str | None = Field(default=None, max_length=80)
    torque_ncm: int | None = Field(default=None, ge=0, le=150)
    isq: int | None = Field(default=None, ge=1, le=100)
    injerto_oseo: bool = False
    material_injerto: str | None = None
    membrana: bool = False
    garantia_hasta: date | None = None
    notas: str | None = None


def _lote(valor: str | None) -> str | None:
    if valor is None:
        return None
    limpio = valor.strip().upper()
    if not limpio:
        raise ValueError("El lote es obligatorio: es lo que permite la trazabilidad")
    return limpio


class ImplanteCrear(ImplanteCampos):
    model_config = ESTRICTO

    sistema_implante_id: int
    lote: str = Field(min_length=1, max_length=60)
    procedimiento_id: int | None = Field(
        default=None, description="La línea de consulta en la que se colocó"
    )
    codigo_fdi: int | None = Field(default=None, description="Por defecto, la pieza de la línea")
    doctor_id: int | None = Field(default=None, description="Por defecto, el de la línea")
    fecha_colocacion: date | None = Field(default=None, description="Por defecto, la de la línea")
    estado: EstadoImplante = EstadoImplante.COLOCADO

    _limpiar_lote = field_validator("lote")(_lote)


class ImplanteActualizar(ImplanteCampos):
    model_config = ESTRICTO

    sistema_implante_id: int | None = None
    lote: str | None = Field(default=None, min_length=1, max_length=60)
    injerto_oseo: bool | None = None
    membrana: bool | None = None
    fecha_colocacion: date | None = None
    fecha_carga: date | None = None
    estado: EstadoImplante | None = None

    _limpiar_lote = field_validator("lote")(_lote)


class ImplanteLeer(ImplanteCampos):
    model_config = ORM

    id: int
    paciente_id: int
    doctor_id: int
    doctor_nombre: str
    procedimiento_id: int | None
    sistema_implante_id: int
    sistema_nombre: str
    codigo_fdi: int
    lote: str
    injerto_oseo: bool | None
    membrana: bool | None
    fecha_colocacion: date | None
    fecha_carga: date | None
    estado: EstadoImplante
    eventos: list[EventoLeer] = []


class ImplanteConPaciente(ImplanteLeer):
    """Para la búsqueda por lote: a quién hay que llamar ante un retiro."""

    paciente_codigo: str
    paciente_nombre: str
    paciente_telefono: str | None
