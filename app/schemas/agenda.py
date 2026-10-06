"""Schemas de la agenda."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import EstadoCita

ORM = ConfigDict(from_attributes=True)
ESTRICTO = ConfigDict(extra="forbid")


class CitaEventoLeer(BaseModel):
    model_config = ORM

    id: int
    tipo: str
    inicio_anterior: datetime | None
    inicio_nuevo: datetime | None
    estado_anterior: EstadoCita | None
    estado_nuevo: EstadoCita | None
    motivo: str | None
    ocurrido_en: datetime


class CitaLeer(BaseModel):
    model_config = ORM

    id: int
    paciente_id: int
    paciente_nombre: str
    paciente_celular: str | None
    doctor_id: int
    doctor_nombre: str
    unidad_id: int | None
    unidad_nombre: str | None
    servicio_id: int | None
    servicio_nombre: str | None
    plan_id: int | None
    inicio: datetime
    fin: datetime
    motivo: str | None
    estado: EstadoCita
    notas: str | None
    sobrecupo: bool
    sobrecupo_motivo: str | None
    recordatorio_enviado_en: datetime | None
    siguientes: list[EstadoCita]


class CitaDetalle(CitaLeer):
    eventos: list[CitaEventoLeer] = []


class _Horario(BaseModel):
    """La cita se agenda con inicio y duración: la hora de fin la calcula el servidor."""

    inicio: datetime | None = None
    duracion_min: int | None = Field(
        default=None, ge=5, le=480, description="Por defecto, la del servicio; si no, 30"
    )

    @model_validator(mode="after")
    def _con_zona(self):
        if self.inicio is not None and self.inicio.tzinfo is None:
            raise ValueError("inicio debe llevar zona horaria")
        return self


class CitaCrear(_Horario):
    model_config = ESTRICTO

    paciente_id: int
    doctor_id: int
    inicio: datetime
    unidad_id: int | None = None
    servicio_id: int | None = None
    plan_id: int | None = None
    motivo: str | None = None
    notas: str | None = None
    estado: EstadoCita = EstadoCita.AGENDADA
    sobrecupo: bool = False
    sobrecupo_motivo: str | None = None


class CitaActualizar(_Horario):
    """PATCH. Cambiar `inicio` o `duracion_min` es reprogramar: deja rastro."""

    model_config = ESTRICTO

    doctor_id: int | None = None
    unidad_id: int | None = None
    servicio_id: int | None = None
    motivo: str | None = None
    notas: str | None = None
    sobrecupo: bool | None = None
    sobrecupo_motivo: str | None = None
    motivo_cambio: str | None = Field(default=None, description="Por qué se reprograma")


class CambioEstado(BaseModel):
    model_config = ESTRICTO

    estado: EstadoCita
    motivo: str | None = None


class ClinicaLeer(BaseModel):
    """La sede principal: membrete de impresos y firma de mensajes."""

    model_config = ORM

    id: int
    nombre: str
    direccion: str | None
    ciudad: str | None
    telefono: str | None
    whatsapp: str | None
    email: str | None
    web: str | None
    rnc: str | None
    logo_archivo_id: int | None = Field(
        default=None, description="Archivo del logo; lo piden con sesión los impresos y el menú"
    )
