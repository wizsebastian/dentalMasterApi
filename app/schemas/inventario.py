"""Schemas de gastos, insumos, kárdex e informes."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.cuenta import Metodo

ORM = ConfigDict(from_attributes=True)
ESTRICTO = ConfigDict(extra="forbid")

TipoGasto = Literal["consultorio", "doctor", "personal"]
MotivoManual = Literal["compra", "merma", "conteo", "devolucion", "inicial"]


class NombreLeer(BaseModel):
    model_config = ORM

    id: int
    nombre: str


class NombreCrear(BaseModel):
    model_config = ESTRICTO

    nombre: str = Field(min_length=1, max_length=80)


class ProveedorLeer(BaseModel):
    model_config = ORM

    id: int
    nombre: str
    rnc: str | None
    telefono: str | None


# --- Gastos --------------------------------------------------------------------


class CompraEscribir(BaseModel):
    """Lo que el gasto trajo al almacén: una entrada de kárdex por renglón."""

    model_config = ESTRICTO

    insumo_id: int
    cantidad: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    costo_unit: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class GastoCrear(BaseModel):
    model_config = ESTRICTO

    fecha: date | None = Field(default=None, description="Por defecto, hoy")
    monto: Decimal = Field(gt=0, max_digits=12, decimal_places=2, description="ITBIS incluido")
    itbis: Decimal = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=2)
    categoria_id: int
    descripcion: str = Field(min_length=1, max_length=200)
    tipo: TipoGasto = "consultorio"
    doctor_id: int | None = Field(default=None, description="Obligatorio si el tipo es doctor")
    paciente_id: int | None = None
    metodo: Metodo = "efectivo"
    proveedor: str | None = Field(default=None, description="Nombre; se crea si no existe")
    proveedor_rnc: str | None = None
    tipo_ncf: str | None = None
    ncf: str | None = Field(default=None, pattern=r"^(B[0-9]{10}|E[0-9]{12})$")
    notas: str | None = None
    compras: list[CompraEscribir] = []


class GastoLeer(BaseModel):
    model_config = ORM

    id: int
    fecha: date
    monto: Decimal
    itbis: Decimal
    categoria_id: int
    categoria_nombre: str
    descripcion: str
    tipo: TipoGasto
    doctor_id: int | None
    doctor_nombre: str | None
    paciente_id: int | None
    metodo: str
    proveedor_nombre: str | None
    tipo_ncf: str | None
    ncf: str | None
    comprobante_id: int | None = None
    notas: str | None
    anulado_en: datetime | None
    motivo_anulacion: str | None


class GastoAnular(BaseModel):
    model_config = ESTRICTO

    motivo: str = Field(min_length=3, max_length=300)


class TotalPorNombre(BaseModel):
    nombre: str
    gastos: int
    monto: Decimal


class Gastos(BaseModel):
    desde: date
    hasta: date
    total: Decimal
    itbis: Decimal
    por_tipo: list[TotalPorNombre]
    por_categoria: list[TotalPorNombre]
    items: list[GastoLeer]


# --- Insumos -------------------------------------------------------------------


class InsumoBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=160)
    categoria_id: int | None = None
    marca: str | None = None
    modelo: str | None = None
    unidad: str = Field(default="unidad", min_length=1, max_length=40)
    controla_stock: bool = True
    stock_minimo: Decimal = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=3)
    costo: Decimal = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=2)
    notas: str | None = None


class InsumoCrear(InsumoBase):
    model_config = ESTRICTO

    existencia_inicial: Decimal = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=3)


class InsumoActualizar(BaseModel):
    """La existencia no se edita: se mueve con un asiento de kárdex."""

    model_config = ESTRICTO

    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    categoria_id: int | None = None
    marca: str | None = None
    modelo: str | None = None
    unidad: str | None = Field(default=None, min_length=1, max_length=40)
    controla_stock: bool | None = None
    stock_minimo: Decimal | None = Field(default=None, ge=0)
    costo: Decimal | None = Field(default=None, ge=0)
    notas: str | None = None
    activo: bool | None = None


class InsumoLeer(InsumoBase):
    model_config = ORM

    id: int
    categoria_nombre: str | None
    activo: bool
    existencia: Decimal = Decimal(0)
    valor: Decimal = Decimal(0)
    bajo_minimo: bool = False


class Inventario(BaseModel):
    insumos: int
    bajo_minimo: int
    valor: Decimal
    items: list[InsumoLeer]


class MovimientoCrear(BaseModel):
    """Un asiento manual. En «conteo», `cantidad` es lo que hay en el estante: el
    sistema calcula la diferencia."""

    model_config = ESTRICTO

    motivo: MotivoManual
    cantidad: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    costo_unit: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    nota: str | None = None


class MovimientoLeer(BaseModel):
    model_config = ORM

    id: int
    insumo_id: int
    cantidad: Decimal
    motivo: str
    costo_unit: Decimal | None
    gasto_id: int | None
    procedimiento_id: int | None
    nota: str | None
    ocurrido_en: datetime


class RecetaInsumo(BaseModel):
    model_config = ESTRICTO

    insumo_id: int
    cantidad: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


class RecetaInsumoLeer(BaseModel):
    insumo_id: int
    nombre: str
    unidad: str
    cantidad: Decimal
    costo: Decimal = Field(description="Cantidad por el costo del insumo")


class CostoServicio(BaseModel):
    servicio_id: int
    costo_insumos: Decimal


# --- Informes ------------------------------------------------------------------


class FilaDoctor(BaseModel):
    doctor_id: int
    doctor_nombre: str
    produccion: Decimal = Field(description="Lo ejecutado en el tramo")
    cobrado: Decimal = Field(description="Lo cobrado en el tramo por sus consultas")
    comision_pct: Decimal
    comision: Decimal = Field(description="Cobrado por su porcentaje")
    pagado: Decimal = Field(description="Gastos de tipo doctor ya registrados a su nombre")


class FilaUnidad(BaseModel):
    unidad: str
    consultas: int
    produccion: Decimal


class Resumen(BaseModel):
    """Lo que entró, lo que salió y quién lo produjo, en un tramo de fechas."""

    desde: date
    hasta: date
    ingresos: Decimal
    gastos: Decimal
    neto: Decimal
    produccion: Decimal
    por_cobrar: Decimal = Field(description="Saldo de todos los pacientes, hoy")
    doctores: list[FilaDoctor]
    unidades: list[FilaUnidad]
