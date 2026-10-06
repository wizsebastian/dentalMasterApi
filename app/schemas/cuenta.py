"""Schemas de la cuenta del paciente: pagos, recibos y cuentas por cobrar."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ORM = ConfigDict(from_attributes=True)
ESTRICTO = ConfigDict(extra="forbid")

# La misma lista que el CHECK de `pago.metodo`.
Metodo = Literal["efectivo", "tarjeta", "transferencia", "cheque", "seguro", "otro"]


class AplicacionLeer(BaseModel):
    model_config = ORM

    consulta_id: int
    monto: Decimal


class PagoCrear(BaseModel):
    model_config = ESTRICTO

    monto: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    metodo: Metodo = "efectivo"
    fecha: date | None = Field(default=None, description="Por defecto, hoy")
    concepto: str | None = None
    referencia: str | None = Field(default=None, description="Autorización, n.º de transferencia…")
    consulta_id: int | None = Field(
        default=None,
        description="A qué consulta va primero. Sin ella, a las más antiguas con saldo",
    )


class PagoActualizar(BaseModel):
    """Con el recibo emitido sólo se corrige lo que no cambia el dinero."""

    model_config = ESTRICTO

    concepto: str | None = None
    referencia: str | None = None
    metodo: Metodo | None = None


class PagoAnular(BaseModel):
    model_config = ESTRICTO

    motivo: str = Field(min_length=3, max_length=300)


class PagoLeer(BaseModel):
    model_config = ORM

    id: int
    paciente_id: int
    numero_recibo: int
    fecha: date
    metodo: str
    monto: Decimal
    concepto: str | None
    referencia: str | None
    comprobante_id: int | None = None
    registrado_en: datetime
    anulado_en: datetime | None
    motivo_anulacion: str | None
    aplicaciones: list[AplicacionLeer] = []
    sin_aplicar: Decimal = Field(default=Decimal(0), description="Lo que quedó como anticipo")


class PagoConPaciente(PagoLeer):
    """Para listados de caja y para el recibo."""

    paciente_nombre: str
    paciente_documento: str | None
    paciente_telefono: str | None
    recibido_por_email: str | None


class Recibo(PagoConPaciente):
    balance_despues: Decimal = Field(description="Balance del paciente hoy, tras este pago")


class ConsultaConSaldo(BaseModel):
    consulta_id: int
    fecha: datetime
    descripcion: str
    total: Decimal
    aplicado: Decimal
    saldo: Decimal


class EstadoDeCuenta(BaseModel):
    """Lo que el paciente debe y lo que ha pagado. `balance` negativo es crédito a favor."""

    paciente_id: int
    cargos: Decimal
    pagado: Decimal
    credito_sin_aplicar: Decimal
    balance: Decimal
    pagos: list[PagoLeer]
    pendientes: list[ConsultaConSaldo]


class CuentaPorCobrar(BaseModel):
    paciente_id: int
    paciente_nombre: str
    paciente_codigo: str
    paciente_telefono: str | None
    consultas: int = Field(description="Consultas con saldo")
    cargos: Decimal
    pagado: Decimal
    balance: Decimal
    desde: datetime | None = Field(description="Fecha de la consulta con saldo más antigua")
    dias: int | None = Field(description="Antigüedad de esa consulta")


class TramoAntiguedad(BaseModel):
    etiqueta: str
    pacientes: int
    balance: Decimal


class CuentasPorCobrar(BaseModel):
    total: Decimal
    pacientes: int
    antiguedad: list[TramoAntiguedad]
    items: list[CuentaPorCobrar]


class TotalMetodo(BaseModel):
    metodo: str
    pagos: int
    monto: Decimal


class Caja(BaseModel):
    """Lo cobrado en un tramo de fechas, para el cierre de caja."""

    desde: date
    hasta: date
    total: Decimal
    anulados: int
    por_metodo: list[TotalMetodo]
    pagos: list[PagoConPaciente]
