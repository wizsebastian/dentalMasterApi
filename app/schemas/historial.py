"""Schemas de consultas, sus líneas ejecutadas y los planes de tratamiento."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import EstadoPlan, EstadoProcedimiento

ORM = ConfigDict(from_attributes=True)
ESTRICTO = ConfigDict(extra="forbid")

Importe = Field(default=None, ge=0, max_digits=12, decimal_places=2)
Porcentaje = Field(default=Decimal(0), ge=0, le=100, max_digits=5, decimal_places=2)


def _superficies(valor: str | None) -> str | None:
    """Caras como texto compacto, sin repetir y en mayúsculas: 'mod' → 'MOD'."""
    if valor is None:
        return None
    limpio = "".join(dict.fromkeys(valor.upper().replace(" ", "")))
    if not limpio:
        return None
    if set(limpio) - set("MDVLOI"):
        raise ValueError("Las caras válidas son M, D, V, L, O e I")
    return limpio


# --- Líneas de una consulta ----------------------------------------------------


class LineaEscribir(BaseModel):
    """Un servicio ejecutado. Sin `precio`, se toma el de la tarifa."""

    model_config = ESTRICTO

    id: int | None = Field(default=None, description="Al editar: la línea que se conserva")
    servicio_id: int
    codigo_fdi: int | None = None
    superficies: str | None = None
    cantidad: int = Field(default=1, ge=1, le=99)
    precio: Decimal | None = Importe
    descuento_pct: Decimal = Porcentaje
    plan_item_id: int | None = None
    notas: str | None = None

    _caras = field_validator("superficies")(_superficies)


class LineaLeer(BaseModel):
    model_config = ORM

    id: int
    servicio_id: int
    servicio_codigo: str
    servicio_nombre: str
    codigo_fdi: int | None
    superficies: str | None
    cantidad: int
    precio: Decimal
    descuento_pct: Decimal
    total: Decimal
    plan_item_id: int | None
    estado: EstadoProcedimiento
    notas: str | None
    es_implante: bool = False
    implante_id: int | None = Field(
        default=None, description="Implante ya registrado para esta línea, con su lote"
    )


# --- Consultas -----------------------------------------------------------------


class ConsultaCampos(BaseModel):
    motivo: str | None = None
    diagnostico: str | None = None
    plan: str | None = Field(default=None, description="Tratamiento realizado e indicaciones")
    notas: str | None = None
    subjetivo: str | None = None
    objetivo: str | None = None
    presion_sistolica: int | None = Field(default=None, ge=40, le=300)
    presion_diastolica: int | None = Field(default=None, ge=20, le=200)
    pulso: int | None = Field(default=None, ge=20, le=250)
    temperatura: Decimal | None = Field(default=None, ge=30, le=45)


class ConsultaCrear(ConsultaCampos):
    model_config = ESTRICTO

    doctor_id: int
    fecha: datetime | None = Field(default=None, description="Por defecto, ahora. Puede ser pasada")
    plan_id: int | None = Field(default=None, description="Sin plan, la consulta queda suelta")
    unidad_id: int | None = None
    cita_id: int | None = None
    lineas: list[LineaEscribir] = []


class ConsultaActualizar(ConsultaCampos):
    """PATCH. Si viaja `lineas`, reemplaza las de la consulta: las que traen `id`
    se conservan y actualizan, las demás se crean, y las que falten se quitan."""

    model_config = ESTRICTO

    doctor_id: int | None = None
    fecha: datetime | None = None
    plan_id: int | None = None
    unidad_id: int | None = None
    lineas: list[LineaEscribir] | None = None


class ConsultaLeer(ConsultaCampos):
    model_config = ORM

    id: int
    paciente_id: int
    doctor_id: int
    doctor_nombre: str
    plan_id: int | None
    unidad_id: int | None
    unidad_nombre: str | None
    cita_id: int | None
    fecha: datetime
    lineas: list[LineaLeer] = []
    # De `v_saldo_consulta`: lo cobrado no se calcula en la interfaz.
    total: Decimal = Decimal(0)
    aplicado: Decimal = Decimal(0)
    saldo: Decimal = Decimal(0)


# --- Planes de tratamiento -----------------------------------------------------


class ItemEscribir(BaseModel):
    model_config = ESTRICTO

    servicio_id: int
    codigo_fdi: int | None = None
    superficies: str | None = None
    cantidad: int = Field(default=1, ge=1, le=99)
    precio_unit: Decimal | None = Importe
    descuento_pct: Decimal = Porcentaje
    fase: int = Field(default=1, ge=1, le=9)
    prioridad: int = Field(default=3, ge=1, le=5)
    aprobado: bool = False

    _caras = field_validator("superficies")(_superficies)


class ItemActualizar(BaseModel):
    model_config = ESTRICTO

    codigo_fdi: int | None = None
    superficies: str | None = None
    cantidad: int | None = Field(default=None, ge=1, le=99)
    precio_unit: Decimal | None = Importe
    descuento_pct: Decimal | None = Field(default=None, ge=0, le=100)
    fase: int | None = Field(default=None, ge=1, le=9)
    prioridad: int | None = Field(default=None, ge=1, le=5)
    aprobado: bool | None = None

    _caras = field_validator("superficies")(_superficies)


class ItemLeer(BaseModel):
    model_config = ORM

    id: int
    servicio_id: int
    servicio_codigo: str
    servicio_nombre: str
    codigo_fdi: int | None
    superficies: str | None
    cantidad: int
    precio_unit: Decimal
    descuento_pct: Decimal
    fase: int
    prioridad: int
    aprobado: bool
    total: Decimal
    ejecutado: bool = Field(default=False, description="Ya hay una línea de consulta que lo cumple")


class PlanCrear(BaseModel):
    model_config = ESTRICTO

    doctor_id: int
    titulo: str | None = Field(default=None, max_length=120)
    especialidad_id: int | None = None
    lista_precio_id: int | None = Field(default=None, description="Por defecto, la particular")
    descuento_pct: Decimal = Porcentaje
    notas: str | None = None


class PlanActualizar(BaseModel):
    model_config = ESTRICTO

    doctor_id: int | None = None
    titulo: str | None = Field(default=None, max_length=120)
    especialidad_id: int | None = None
    descuento_pct: Decimal | None = Field(default=None, ge=0, le=100)
    notas: str | None = None
    estado: EstadoPlan | None = None


class PlanLeer(BaseModel):
    model_config = ORM

    id: int
    codigo: str
    paciente_id: int
    doctor_id: int
    doctor_nombre: str
    especialidad_id: int | None
    especialidad_nombre: str | None
    lista_precio_id: int
    titulo: str | None
    fecha: date
    estado: EstadoPlan
    siguientes: list[EstadoPlan]
    descuento_pct: Decimal
    notas: str | None
    cerrado_en: datetime | None
    items: list[ItemLeer] = []
    cotizado: Decimal = Field(
        default=Decimal(0), description="Suma de los ítems, sin el descuento del plan"
    )
    total: Decimal = Field(default=Decimal(0), description="Cotizado menos el descuento del plan")
    ejecutado: Decimal = Field(
        default=Decimal(0), description="Lo ya hecho en las consultas del plan"
    )
    lista_precio_nombre: str = ""
    aseguradora_nombre: str | None = Field(
        default=None, description="Si el plan se cotizó con la tarifa de una ARS"
    )
    cobertura_estimada: Decimal = Field(
        default=Decimal(0),
        description="Lo que cubriría el seguro según la tarifa; el resto es copago",
    )


class PlanConConsultas(PlanLeer):
    consultas: list[ConsultaLeer] = []


class Historial(BaseModel):
    """El historial del paciente: sus planes con sus consultas, y las consultas sueltas."""

    planes: list[PlanConConsultas]
    sueltas: list[ConsultaLeer]
