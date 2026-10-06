"""Schemas de paciente, contactos y ficha médica."""

import re
from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.telefono import Telefono
from app.core.tiempo import hoy
from app.models.enums import Sexo

ORM = ConfigDict(from_attributes=True)


def normalizar_documento(valor: str | None) -> str | None:
    """Cédula o pasaporte. Vacío es válido; un relleno no.

    El documento es opcional precisamente para que nadie tenga que inventarlo:
    donde es obligatorio se acaba escribiendo `000000000000`, que además choca
    con la unicidad en la segunda alta. Una cédula dominicana (11 dígitos) se
    guarda siempre como 000-0000000-0.
    """
    if valor is None:
        return None
    valor = valor.strip()
    if not valor:
        return None

    significativos = re.sub(r"[\s\-./]", "", valor)
    if len(significativos) < 5 or len(set(significativos)) < 2:
        raise ValueError("El documento parece un relleno; déjalo vacío si no se conoce")

    if significativos.isdigit() and len(significativos) == 11:
        return f"{significativos[:3]}-{significativos[3:10]}-{significativos[10]}"
    return valor.upper()


class ContactoBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    parentesco: str | None = None
    # Sólo se lee (no hay alta de contactos por la API): un valor guardado antes del
    # formato nuevo no debe romper la lectura del paciente.
    telefono: str = Field(min_length=1, max_length=40)
    es_emergencia: bool = True
    es_tutor: bool = False


class ContactoLeer(ContactoBase):
    model_config = ORM
    id: int


class PacienteBase(BaseModel):
    nombres: str = Field(min_length=1, max_length=120)
    apellidos: str = Field(min_length=1, max_length=120)
    # Opcionales: el alta rápida sólo pide el nombre.
    fecha_nacimiento: date | None = None
    sexo: Sexo | None = None
    documento: str | None = None
    telefono: Telefono = None
    celular: Telefono = None
    email: EmailStr | None = None
    direccion: str | None = None
    ciudad: str | None = None
    ocupacion: str | None = None
    estado_civil: str | None = None
    tipo_sangre: str | None = None
    referido_por: str | None = None
    sede_id: int | None = None
    doctor_tratante_id: int | None = None
    notas: str | None = None

    @field_validator("fecha_nacimiento")
    @classmethod
    def _no_futura(cls, valor: date | None) -> date | None:
        if valor is not None and valor > hoy():
            raise ValueError("La fecha de nacimiento no puede estar en el futuro")
        return valor

    @field_validator("documento")
    @classmethod
    def _documento(cls, valor: str | None) -> str | None:
        return normalizar_documento(valor)


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
    telefono: Telefono = None
    celular: Telefono = None
    email: EmailStr | None = None
    direccion: str | None = None
    ciudad: str | None = None
    ocupacion: str | None = None
    estado_civil: str | None = None
    tipo_sangre: str | None = None
    referido_por: str | None = None
    sede_id: int | None = None
    doctor_tratante_id: int | None = None
    notas: str | None = None
    activo: bool | None = None

    @field_validator("fecha_nacimiento")
    @classmethod
    def _no_futura(cls, valor: date | None) -> date | None:
        if valor is not None and valor > hoy():
            raise ValueError("La fecha de nacimiento no puede estar en el futuro")
        return valor

    @field_validator("documento")
    @classmethod
    def _documento(cls, valor: str | None) -> str | None:
        return normalizar_documento(valor)


class PacienteResumen(BaseModel):
    """Fila del listado: lo justo para buscar y elegir."""

    model_config = ORM

    id: int
    codigo: str
    documento: str | None
    nombres: str
    apellidos: str
    fecha_nacimiento: date | None
    edad: int | None
    sexo: Sexo | None
    telefono: str | None
    celular: str | None
    doctor_tratante_id: int | None
    doctor_tratante_nombre: str | None
    activo: bool


class PacienteDetalle(PacienteResumen):
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
