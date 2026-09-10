"""Schemas de paciente, contactos y ficha médica."""

from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import Sexo

ORM = ConfigDict(from_attributes=True)


class ContactoBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    parentesco: str | None = None
    telefono: str = Field(min_length=1, max_length=40)
    es_emergencia: bool = True
    es_tutor: bool = False


class ContactoLeer(ContactoBase):
    model_config = ORM
    id: int


class PacienteBase(BaseModel):
    nombres: str = Field(min_length=1, max_length=120)
    apellidos: str = Field(min_length=1, max_length=120)
    fecha_nacimiento: date
    sexo: Sexo
    documento: str | None = None
    telefono: str | None = None
    celular: str | None = None
    email: EmailStr | None = None
    direccion: str | None = None
    ciudad: str | None = None
    ocupacion: str | None = None
    estado_civil: str | None = None
    tipo_sangre: str | None = None
    referido_por: str | None = None
    sede_id: int | None = None
    notas: str | None = None

    @field_validator("fecha_nacimiento")
    @classmethod
    def _no_futura(cls, valor: date) -> date:
        if valor > date.today():
            raise ValueError("La fecha de nacimiento no puede estar en el futuro")
        return valor


class PacienteCrear(PacienteBase):
    """El `codigo` de expediente lo genera el servidor: no se acepta del cliente."""


class PacienteActualizar(BaseModel):
    """Todos los campos opcionales: es un PATCH."""

    model_config = ConfigDict(extra="forbid")

    nombres: str | None = Field(default=None, min_length=1, max_length=120)
    apellidos: str | None = Field(default=None, min_length=1, max_length=120)
    fecha_nacimiento: date | None = None
    sexo: Sexo | None = None
    documento: str | None = None
    telefono: str | None = None
    celular: str | None = None
    email: EmailStr | None = None
    direccion: str | None = None
    ciudad: str | None = None
    ocupacion: str | None = None
    estado_civil: str | None = None
    tipo_sangre: str | None = None
    referido_por: str | None = None
    sede_id: int | None = None
    notas: str | None = None
    activo: bool | None = None


class PacienteResumen(BaseModel):
    """Fila del listado: lo justo para buscar y elegir."""

    model_config = ORM

    id: int
    codigo: str
    documento: str | None
    nombres: str
    apellidos: str
    fecha_nacimiento: date
    edad: int
    sexo: Sexo
    celular: str | None
    activo: bool


class PacienteDetalle(PacienteResumen):
    telefono: str | None
    email: str | None
    direccion: str | None
    ciudad: str | None
    ocupacion: str | None
    estado_civil: str | None
    tipo_sangre: str | None
    referido_por: str | None
    sede_id: int | None
    notas: str | None
    contactos: list[ContactoLeer] = []


class Alerta(BaseModel):
    """Aviso clínico que se muestra antes de cualquier procedimiento."""

    model_config = ORM

    tipo: str  # 'condicion' | 'alergia'
    detalle: str
    riesgo: str | None
