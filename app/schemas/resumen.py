"""Schemas del resumen del paciente y de sus seguros."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import EstadoCita, EstadoImplante, EstadoPlan

ORM = ConfigDict(from_attributes=True)
ESTRICTO = ConfigDict(extra="forbid")


# --- Seguros -------------------------------------------------------------------


class SeguroEscribir(BaseModel):
    model_config = ESTRICTO

    aseguradora_id: int
    poliza: str = Field(min_length=1, max_length=60)
    plan: str | None = Field(default=None, max_length=80)
    titular: str | None = Field(default=None, max_length=120)
    vigente_desde: date | None = None
    vigente_hasta: date | None = None
    principal: bool = True

    @model_validator(mode="after")
    def _vigencia(self) -> "SeguroEscribir":
        if self.vigente_desde and self.vigente_hasta and self.vigente_hasta < self.vigente_desde:
            raise ValueError("vigente_hasta: anterior al inicio de la vigencia")
        return self


class SeguroLeer(BaseModel):
    model_config = ORM

    id: int
    aseguradora_id: int
    aseguradora_nombre: str
    poliza: str
    plan: str | None
    titular: str | None
    vigente_desde: date | None
    vigente_hasta: date | None
    principal: bool
    vigente: bool = True


# --- Resumen -------------------------------------------------------------------


class ResumenConsulta(BaseModel):
    id: int
    fecha: datetime
    doctor_nombre: str
    motivo: str | None
    diagnostico: str | None
    servicios: list[str]


class ResumenCita(BaseModel):
    id: int
    inicio: datetime
    doctor_nombre: str
    servicio_nombre: str | None
    estado: EstadoCita


class ResumenPlan(BaseModel):
    id: int
    codigo: str
    titulo: str | None
    estado: EstadoPlan
    items: int
    hechos: int
    total: Decimal
    pendiente: Decimal = Field(description="Lo cotizado que aún no se ha ejecutado")
    siguiente: str | None = Field(description="El próximo paso, según fase y prioridad")


class ResumenImplante(BaseModel):
    id: int
    codigo_fdi: int
    sistema_nombre: str
    lote: str
    estado: EstadoImplante
    fecha_colocacion: date | None


class ResumenClinico(BaseModel):
    """El paciente de un vistazo. Todo se calcula: nada de esto se redacta."""

    paciente_id: int
    primera_visita: date | None
    consultas: int
    ausencias: int = Field(description="Citas a las que no asistió")
    ultima_consulta: ResumenConsulta | None
    proxima_cita: ResumenCita | None
    planes: list[ResumenPlan]
    implantes: list[ResumenImplante]
    seguro: SeguroLeer | None
    balance: Decimal
    credito_sin_aplicar: Decimal
    por_firmar: int = Field(description="Documentos emitidos que esperan firma")
    archivos: int
