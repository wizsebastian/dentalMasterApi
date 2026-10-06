"""Schemas de comprobantes fiscales (NCF) y del cierre de caja."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import EstadoFactura

ORM = ConfigDict(from_attributes=True)
ESTRICTO = ConfigDict(extra="forbid")

# Los que la clínica emite a mano. La serie E (e-CF) exige firma digital y envío
# a la DGII: la tabla admite sus rangos, pero aquí no se emiten.
TipoNcf = Literal["B01", "B02", "B14", "B15"]

ETIQUETA_NCF: dict[str, str] = {
    "B01": "Crédito fiscal",
    "B02": "Consumo",
    "B14": "Régimen especial",
    "B15": "Gubernamental",
}


# --- Secuencias ----------------------------------------------------------------


class SecuenciaLeer(BaseModel):
    model_config = ORM

    id: int
    tipo: str
    desde: int
    hasta: int
    siguiente: int
    disponibles: int
    vence: date | None
    activo: bool


class SecuenciaCrear(BaseModel):
    """Un rango nuevo autorizado por la DGII. Sustituye al activo de su tipo."""

    model_config = ESTRICTO

    tipo: TipoNcf
    desde: int = Field(ge=1, le=99_999_999)
    hasta: int = Field(ge=1, le=99_999_999)
    vence: date | None = None

    @model_validator(mode="after")
    def _rango(self) -> "SecuenciaCrear":
        if self.hasta < self.desde:
            raise ValueError("hasta: el final del rango es anterior al inicio")
        return self


class SecuenciaActualizar(BaseModel):
    model_config = ESTRICTO

    vence: date | None = None
    activo: bool | None = None


# --- Facturas ------------------------------------------------------------------


class LineaFacturable(BaseModel):
    """Una línea ejecutada que todavía no está en ningún comprobante."""

    procedimiento_id: int
    consulta_id: int
    fecha: date
    descripcion: str
    cantidad: int
    precio: Decimal
    descuento_pct: Decimal
    total: Decimal


class FacturaCrear(BaseModel):
    model_config = ESTRICTO

    tipo_ncf: TipoNcf = "B02"
    procedimiento_ids: list[int] = Field(min_length=1)
    rnc_cliente: str | None = None
    razon_social: str | None = Field(default=None, max_length=160)

    @field_validator("rnc_cliente")
    @classmethod
    def _rnc(cls, valor: str | None) -> str | None:
        if valor is None or not valor.strip():
            return None
        digitos = re.sub(r"\D", "", valor)
        if len(digitos) not in (9, 11):
            raise ValueError("El RNC tiene 9 dígitos; la cédula, 11")
        return digitos

    @model_validator(mode="after")
    def _credito_fiscal(self) -> "FacturaCrear":
        if self.tipo_ncf != "B02" and not (self.rnc_cliente and (self.razon_social or "").strip()):
            raise ValueError(
                "rnc_cliente: un comprobante que no es de consumo lleva RNC y razón social"
            )
        if len(set(self.procedimiento_ids)) != len(self.procedimiento_ids):
            raise ValueError("procedimiento_ids: hay líneas repetidas")
        return self


class FacturaAnular(BaseModel):
    model_config = ESTRICTO

    motivo: str = Field(min_length=3, max_length=300)


class FacturaItemLeer(BaseModel):
    model_config = ORM

    id: int
    procedimiento_id: int | None
    descripcion: str
    cantidad: int
    precio_unit: Decimal
    descuento_pct: Decimal
    tasa_impuesto: Decimal
    total: Decimal


class FacturaLeer(BaseModel):
    model_config = ORM

    id: int
    paciente_id: int
    numero: str
    tipo_ncf: str | None
    ncf_vence: date | None
    rnc_cliente: str | None
    razon_social: str | None
    fecha: date
    subtotal: Decimal
    descuento: Decimal
    impuesto: Decimal
    total: Decimal
    estado: EstadoFactura
    anulada_en: datetime | None
    motivo_anulacion: str | None
    items: list[FacturaItemLeer] = []


class Emisor(BaseModel):
    nombre: str
    rnc: str | None
    direccion: str | None
    ciudad: str | None
    telefono: str | None


class FacturaImprimible(FacturaLeer):
    """La factura con lo que hace falta para imprimirla."""

    tipo_etiqueta: str
    emisor: Emisor
    paciente_nombre: str
    paciente_codigo: str
    paciente_documento: str | None
    paciente_direccion: str | None


class FacturasDelPaciente(BaseModel):
    facturas: list[FacturaLeer]
    facturables: list[LineaFacturable]


# --- Cierre de caja ------------------------------------------------------------


class CierreCrear(BaseModel):
    model_config = ESTRICTO

    fecha: date | None = Field(default=None, description="Por defecto, hoy")
    efectivo_contado: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    notas: str | None = Field(default=None, max_length=500)


class CierreLeer(BaseModel):
    model_config = ORM

    id: int
    fecha: date
    cobrado: Decimal
    efectivo_esperado: Decimal
    efectivo_contado: Decimal
    diferencia: Decimal
    desglose: dict[str, Decimal]
    notas: str | None
    cerrado_en: datetime
    cerrado_por_email: str | None = None


class CajaDelDia(BaseModel):
    """La caja viva de un día y, si ya se cerró, la foto del cierre."""

    fecha: date
    cobrado: Decimal
    por_metodo: dict[str, Decimal]
    efectivo_cobrado: Decimal
    gastos_efectivo: Decimal
    efectivo_esperado: Decimal
    cierre: CierreLeer | None
    movido_tras_cierre: Decimal = Field(
        default=Decimal(0), description="Lo cobrado o anulado después de cerrar"
    )
