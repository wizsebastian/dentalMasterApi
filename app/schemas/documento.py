"""Schemas de plantillas, documentos emitidos, firmas y recetas."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ORM = ConfigDict(from_attributes=True)
ESTRICTO = ConfigDict(extra="forbid")

TipoDocumento = Literal[
    "constancia", "licencia", "postoperatorio", "consentimiento", "consentimiento_datos"
]
RolFirmante = Literal["paciente", "tutor", "doctor", "testigo"]


class PlantillaLeer(BaseModel):
    model_config = ORM

    id: int
    codigo: str
    tipo: TipoDocumento
    titulo: str
    cuerpo: str
    requiere_firma: bool
    activo: bool


class PlantillaEscribir(BaseModel):
    model_config = ESTRICTO

    tipo: TipoDocumento
    titulo: str = Field(min_length=1, max_length=160)
    cuerpo: str = Field(min_length=1)
    requiere_firma: bool = False


class PlantillaActualizar(BaseModel):
    model_config = ESTRICTO

    titulo: str | None = Field(default=None, min_length=1, max_length=160)
    cuerpo: str | None = Field(default=None, min_length=1)
    requiere_firma: bool | None = None
    activo: bool | None = None


class Borrador(BaseModel):
    """La plantilla ya combinada con los datos del paciente, lista para revisar."""

    plantilla_id: int
    tipo: TipoDocumento
    titulo: str
    cuerpo: str
    requiere_firma: bool


class DocumentoCrear(BaseModel):
    model_config = ESTRICTO

    tipo: TipoDocumento
    titulo: str = Field(min_length=1, max_length=160)
    cuerpo: str = Field(min_length=1)
    plantilla_id: int | None = None
    consulta_id: int | None = None
    plan_id: int | None = None
    doctor_id: int | None = None
    requiere_firma: bool = False


class FirmaLeer(BaseModel):
    model_config = ORM

    id: int
    firmante_nombre: str
    firmante_rol: str
    firmante_documento: str | None
    trazo: list
    firmado_en: datetime


class DocumentoLeer(BaseModel):
    model_config = ORM

    id: int
    paciente_id: int
    tipo: TipoDocumento
    titulo: str
    cuerpo: str
    consulta_id: int | None
    plan_id: int | None
    doctor_id: int | None
    requiere_firma: bool
    sha256: str
    emitido_en: datetime
    anulado_en: datetime | None
    motivo_anulacion: str | None
    firmas: list[FirmaLeer] = []


class DocumentoAnular(BaseModel):
    model_config = ESTRICTO

    motivo: str = Field(min_length=3, max_length=300)


class EnlaceFirma(BaseModel):
    token: str
    minutos: int = Field(description="Cuánto dura el enlace")


class DocumentoParaFirmar(BaseModel):
    """Lo que ve quien firma, sin sesión: el documento y nada más del expediente."""

    titulo: str
    cuerpo: str
    paciente_nombre: str
    clinica_nombre: str | None
    ya_firmado: bool


class FirmaCrear(BaseModel):
    model_config = ESTRICTO

    firmante_nombre: str = Field(min_length=3, max_length=160)
    firmante_rol: RolFirmante = "paciente"
    firmante_documento: str | None = None
    # Lista de trazos; cada trazo, lista de puntos [x, y].
    trazo: list[list[tuple[float, float]]] = Field(min_length=1)


# --- Recetas -------------------------------------------------------------------


class RecetaItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    medicamento: str = Field(min_length=1, max_length=160)
    presentacion: str | None = None
    dosis: str = Field(min_length=1, max_length=120)
    frecuencia: str = Field(min_length=1, max_length=120)
    duracion: str | None = None


class RecetaCrear(BaseModel):
    model_config = ESTRICTO

    doctor_id: int
    consulta_id: int | None = None
    indicaciones: str | None = None
    items: list[RecetaItem] = Field(min_length=1)
    confirmar_alergias: bool = Field(
        default=False, description="Recetar aunque algún medicamento choque con una alergia"
    )


class RecetaLeer(BaseModel):
    model_config = ORM

    id: int
    paciente_id: int
    doctor_id: int
    doctor_nombre: str
    consulta_id: int | None
    fecha: date
    indicaciones: str | None
    items: list[RecetaItem] = []


class DocumentosDelPaciente(BaseModel):
    documentos: list[DocumentoLeer]
    recetas: list[RecetaLeer]
    datos_personales_firmados: bool = Field(
        description="Hay un consentimiento de datos personales vigente y firmado"
    )
