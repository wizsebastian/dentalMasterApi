"""Schemas del odontograma y del catálogo dental que lo alimenta."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AmbitoCondicion, Denticion, EstadoHallazgo

ORM = ConfigDict(from_attributes=True)

# Códigos de cara válidos. El centro de la pieza es 'O' en posteriores e 'I' en
# anteriores; el resto rodea al diente.
SUPERFICIES = ("M", "D", "V", "L", "O", "I")


class DienteLeer(BaseModel):
    model_config = ORM

    codigo_fdi: int
    cuadrante: int
    posicion: int
    denticion: Denticion
    nombre: str
    grupo: str
    arcada: str
    lado: str
    universal: int | None
    centro_oclusal: str = Field(
        description="Cara central de la pieza: 'I' en anteriores, 'O' en posteriores"
    )


class SuperficieLeer(BaseModel):
    model_config = ORM

    codigo: str
    nombre: str
    aplica_a: str


class CondicionDentalLeer(BaseModel):
    model_config = ORM

    id: int
    codigo: str
    nombre: str
    ambito: AmbitoCondicion
    color_hex: str = Field(description="Único origen del color con que se pinta la pieza")
    patologico: bool
    orden: int | None


class Catalogos(BaseModel):
    """Todo lo que el odontograma necesita para dibujarse, en una sola llamada."""

    dientes: list[DienteLeer]
    superficies: list[SuperficieLeer]
    condiciones: list[CondicionDentalLeer]


class HallazgoLeer(BaseModel):
    model_config = ORM

    id: int
    codigo_fdi: int
    superficie: str | None = Field(
        description="Código de cara, o null si el hallazgo aplica a toda la pieza"
    )
    condicion_dental_id: int
    # Aplanados desde el catálogo por las propiedades del modelo: el frontend
    # necesita el color para pintar sin un segundo viaje.
    condicion_codigo: str
    condicion_nombre: str
    color_hex: str
    ambito: AmbitoCondicion
    estado: EstadoHallazgo
    doctor_id: int | None
    fecha: date
    notas: str | None


class HallazgoCrear(BaseModel):
    codigo_fdi: int
    superficie: str | None = None
    condicion_dental_id: int
    estado: EstadoHallazgo = EstadoHallazgo.EXISTENTE
    notas: str | None = None


class HallazgoActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: EstadoHallazgo | None = None
    notas: str | None = None


class DienteEstado(BaseModel):
    """Estado global de una pieza: lo que no pertenece a una cara concreta."""

    model_config = ORM

    codigo_fdi: int
    presente: bool = True
    movilidad: int | None = Field(default=None, ge=0, le=3)
    recesion_mm: Decimal | None = Field(default=None, ge=0, le=30)
    sondaje_mm: Decimal | None = Field(default=None, ge=0, le=30)
    sangrado: bool = False
    notas: str | None = None


class OdontogramaResumen(BaseModel):
    """Fila del historial de versiones."""

    model_config = ORM

    id: int
    version: int
    fecha: date
    denticion: Denticion
    es_actual: bool
    doctor_id: int | None
    observaciones: str | None


class OdontogramaLeer(OdontogramaResumen):
    paciente_id: int
    dientes: list[DienteEstado] = []
    hallazgos: list[HallazgoLeer] = []


class OdontogramaCrear(BaseModel):
    """Crea la versión N+1 del odontograma de un paciente."""

    denticion: Denticion | None = Field(
        default=None,
        description="Por defecto, la de la versión vigente (permanente si es la primera)",
    )
    observaciones: str | None = None
    copiar_hallazgos: bool = Field(
        default=True,
        description=(
            "Arrastra los hallazgos 'existente' y 'completado' de la versión "
            "anterior, y lo planificado por un ítem de un plan. Lo propuesto a mano "
            "no se copia."
        ),
    )
