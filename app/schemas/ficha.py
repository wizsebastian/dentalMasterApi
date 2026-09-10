"""Schemas de la ficha médica."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

ORM = ConfigDict(from_attributes=True)


class CondicionLeer(BaseModel):
    model_config = ORM

    condicion_medica_id: int
    codigo: str
    nombre: str
    riesgo: str | None = None
    alerta: str | None = None
    diagnosticado_en: date | None = None
    controlado: bool | None = None
    detalle: str | None = None


class CondicionEscribir(BaseModel):
    condicion_medica_id: int
    diagnosticado_en: date | None = None
    controlado: bool = True
    detalle: str | None = None


class AlergiaLeer(BaseModel):
    model_config = ORM

    alergia_id: int
    codigo: str
    nombre: str
    tipo: str | None = None
    severidad: str | None = None
    reaccion: str | None = None


class AlergiaEscribir(BaseModel):
    alergia_id: int
    severidad: str = "moderada"
    reaccion: str | None = None


class MedicamentoLeer(BaseModel):
    model_config = ORM

    id: int
    nombre: str
    dosis: str | None = None
    frecuencia: str | None = None
    motivo: str | None = None
    desde: date | None = None
    activo: bool


class MedicamentoEscribir(BaseModel):
    nombre: str = Field(min_length=1)
    dosis: str | None = None
    frecuencia: str | None = None
    motivo: str | None = None
    desde: date | None = None
    activo: bool = True


class FichaCampos(BaseModel):
    """Los campos propios de la ficha, sin las colecciones."""

    motivo_consulta: str | None = None
    enfermedad_actual: str | None = None
    antecedentes_familiares: str | None = None

    fuma: bool = False
    cigarrillos_dia: int | None = Field(default=None, ge=0)
    consume_alcohol: bool = False
    bruxismo: bool = False
    onicofagia: bool = False
    respirador_bucal: bool = False

    ultima_visita_dental: date | None = None
    cepillados_dia: int | None = Field(default=None, ge=0, le=10)
    usa_hilo_dental: bool = False
    sangrado_encias: bool = False
    sensibilidad: bool = False
    dolor_atm: bool = False

    embarazada: bool = False
    semanas_gestacion: int | None = Field(default=None, ge=0, le=45)
    # Campos propios y no condiciones del catálogo: cambian directamente el
    # protocolo de cirugía e implantes.
    anticoagulantes: bool = False
    bifosfonatos: bool = False

    observaciones: str | None = None


class FichaLeer(FichaCampos):
    model_config = ORM

    id: int
    paciente_id: int
    condiciones: list[CondicionLeer] = []
    alergias: list[AlergiaLeer] = []
    medicamentos: list[MedicamentoLeer] = []


class FichaGuardar(FichaCampos):
    """PUT completo de la ficha, colecciones incluidas.

    La ficha es un formulario que el doctor rellena de una vez, no un recurso
    que se parchee campo a campo. Las tres colecciones se reemplazan enteras.
    """

    condiciones: list[CondicionEscribir] = []
    alergias: list[AlergiaEscribir] = []
    medicamentos: list[MedicamentoEscribir] = []
