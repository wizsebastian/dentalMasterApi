"""Cuenta del paciente y comprobantes fiscales.

Lo que el paciente debe son sus procedimientos ejecutados; lo que ha entrado
son sus pagos. La factura es el comprobante fiscal que se emite a petición: no
genera deuda ni recibe pagos.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.catalogo import enum_col
from app.models.enums import EstadoFactura


class PagoAplicacion(Base):
    """Parte de un pago imputada a una consulta."""

    __tablename__ = "pago_aplicacion"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pago_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("pago.id", ondelete="CASCADE"))
    consulta_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("consulta.id"))
    paciente_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("paciente.id"))
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Pago(Base):
    """Dinero que entra. Es del paciente, no de una factura: admite anticipos.

    Nunca se borra ni cambia de monto. Un pago mal registrado se anula —conserva
    su número de recibo y sale de todo balance— y se registra otro.
    """

    __tablename__ = "pago"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("paciente.id"))
    numero_recibo: Mapped[int] = mapped_column(BigInteger, unique=True)
    fecha: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    metodo: Mapped[str] = mapped_column(Text)
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    concepto: Mapped[str | None] = mapped_column(Text)
    referencia: Mapped[str | None] = mapped_column(Text)
    comprobante_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("archivo.id"))
    recibido_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    registrado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anulado_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    motivo_anulacion: Mapped[str | None] = mapped_column(Text)

    aplicaciones: Mapped[list[PagoAplicacion]] = relationship(cascade="all, delete-orphan")


class FacturaItem(Base):
    __tablename__ = "factura_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    factura_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("factura.id", ondelete="CASCADE")
    )
    procedimiento_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("procedimiento.id"))
    servicio_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("servicio.id"))
    descripcion: Mapped[str] = mapped_column(Text)
    cantidad: Mapped[int] = mapped_column(Integer, default=1)
    precio_unit: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    descuento_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    tasa_impuesto: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class Factura(Base):
    """Comprobante fiscal (NCF) sobre líneas ya ejecutadas."""

    __tablename__ = "factura"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("paciente.id"))
    sede_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sede.id"))
    plan_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("plan_tratamiento.id"))
    numero: Mapped[str] = mapped_column(Text, unique=True)  # NCF
    tipo_ncf: Mapped[str | None] = mapped_column(Text)
    ncf_vence: Mapped[date | None] = mapped_column(Date)
    rnc_cliente: Mapped[str | None] = mapped_column(Text)
    razon_social: Mapped[str | None] = mapped_column(Text)
    fecha: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    moneda: Mapped[str] = mapped_column(CHAR(3), default="DOP")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    descuento: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    impuesto: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    cubierto_seguro: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    estado: Mapped[EstadoFactura] = mapped_column(
        enum_col(EstadoFactura, "estado_factura_t"), default=EstadoFactura.EMITIDA
    )
    emitida_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    anulada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anulada_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    motivo_anulacion: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list[FacturaItem]] = relationship(
        cascade="all, delete-orphan", order_by="FacturaItem.id"
    )


class SecuenciaNcf(Base):
    """Rango de NCF autorizado por la DGII. Sólo una activa por tipo."""

    __tablename__ = "secuencia_ncf"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tipo: Mapped[str] = mapped_column(Text)
    desde: Mapped[int] = mapped_column(BigInteger)
    hasta: Mapped[int] = mapped_column(BigInteger)
    siguiente: Mapped[int] = mapped_column(BigInteger)
    vence: Mapped[date | None] = mapped_column(Date)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def disponibles(self) -> int:
        return max(self.hasta - self.siguiente + 1, 0)


class CierreCaja(Base):
    """La foto de la caja de un día. `diferencia` la genera la base."""

    __tablename__ = "cierre_caja"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, unique=True)
    cobrado: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    efectivo_esperado: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    efectivo_contado: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    diferencia: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), Computed("efectivo_contado - efectivo_esperado")
    )
    desglose: Mapped[dict] = mapped_column(JSONB)
    notas: Mapped[str | None] = mapped_column(Text)
    cerrado_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    cerrado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
