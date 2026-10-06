"""Schemas del reporte de un doctor."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class ServicioRealizado(BaseModel):
    servicio_codigo: str
    servicio_nombre: str
    cantidad: int
    produccion: Decimal


class LineaRealizada(BaseModel):
    """Una línea ejecutada por el doctor en el tramo."""

    procedimiento_id: int
    fecha: date
    paciente_id: int
    paciente_nombre: str
    servicio_nombre: str
    codigo_fdi: int | None
    superficies: str | None
    cantidad: int
    total: Decimal


class CobroDelDoctor(BaseModel):
    """Lo que entró en el tramo por una consulta suya: la base de su comisión."""

    fecha: date
    numero_recibo: int
    pago_id: int
    paciente_id: int
    paciente_nombre: str
    consulta_fecha: date
    monto: Decimal


class PagoAlDoctor(BaseModel):
    """Un gasto de tipo doctor registrado a su nombre."""

    gasto_id: int
    fecha: date
    descripcion: str
    metodo: str
    monto: Decimal


class CitasDelDoctor(BaseModel):
    total: int
    atendidas: int
    no_asistio: int
    canceladas: int


class ReporteDoctor(BaseModel):
    """Lo que hizo un doctor en un tramo, lo que se cobró por ello y lo que se le debe.

    Las cifras coinciden con su fila de `GET /informes/resumen`: salen de las
    mismas definiciones. La comisión es sobre lo **cobrado**, no sobre lo producido.
    """

    doctor_id: int
    doctor_nombre: str
    especialidades: list[str]
    desde: date
    hasta: date

    produccion: Decimal = Field(description="Lo ejecutado en el tramo, cobrado o no")
    cobrado: Decimal = Field(description="Lo cobrado en el tramo por sus consultas")
    comision_pct: Decimal
    comision: Decimal
    pagado: Decimal = Field(description="Ya pagado al doctor en el tramo")
    por_liquidar: Decimal = Field(description="Comisión menos lo ya pagado")
    por_cobrar: Decimal = Field(description="Saldo pendiente, hoy, de todas sus consultas")

    consultas: int
    pacientes: int = Field(description="Pacientes distintos atendidos en el tramo")
    citas: CitasDelDoctor

    servicios: list[ServicioRealizado]
    lineas: list[LineaRealizada]
    cobros: list[CobroDelDoctor]
    pagos: list[PagoAlDoctor]
