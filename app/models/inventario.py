"""Gastos, proveedores, insumos y su kárdex."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class CategoriaGasto(Base):
    __tablename__ = "categoria_gasto"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Proveedor(Base):
    __tablename__ = "proveedor"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(Text)
    rnc: Mapped[str | None] = mapped_column(Text, unique=True)
    telefono: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Gasto(Base):
    """Dinero que sale. Como el pago, no se borra: se anula."""

    __tablename__ = "gasto"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    itbis: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    categoria_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("categoria_gasto.id"))
    descripcion: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(Text)  # consultorio | doctor | personal
    doctor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("doctor.id"))
    paciente_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("paciente.id"))
    metodo: Mapped[str] = mapped_column(Text)
    proveedor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("proveedor.id"))
    tipo_ncf: Mapped[str | None] = mapped_column(Text)
    ncf: Mapped[str | None] = mapped_column(Text)
    comprobante_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("archivo.id"))
    notas: Mapped[str | None] = mapped_column(Text)
    registrado_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    registrado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anulado_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    motivo_anulacion: Mapped[str | None] = mapped_column(Text)

    categoria: Mapped[CategoriaGasto] = relationship(lazy="joined")
    proveedor: Mapped[Proveedor | None] = relationship(lazy="joined")
    doctor: Mapped["Doctor | None"] = relationship(lazy="joined")  # noqa: F821

    @property
    def categoria_nombre(self) -> str:
        return self.categoria.nombre

    @property
    def proveedor_nombre(self) -> str | None:
        return self.proveedor.nombre if self.proveedor else None

    @property
    def doctor_nombre(self) -> str | None:
        return self.doctor.nombre_completo if self.doctor else None


class CategoriaInsumo(Base):
    __tablename__ = "categoria_insumo"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(Text)


class Insumo(Base):
    """Material o servicio externo. La existencia no está aquí: es la suma del kárdex."""

    __tablename__ = "insumo"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(Text)
    categoria_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("categoria_insumo.id"))
    marca: Mapped[str | None] = mapped_column(Text)
    modelo: Mapped[str | None] = mapped_column(Text)
    unidad: Mapped[str] = mapped_column(Text, default="unidad")
    controla_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    stock_minimo: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    costo: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    notas: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    categoria: Mapped[CategoriaInsumo | None] = relationship(lazy="joined")

    @property
    def categoria_nombre(self) -> str | None:
        return self.categoria.nombre if self.categoria else None


class MovimientoInsumo(Base):
    """Un asiento del kárdex. Con signo; nunca se actualiza ni se borra."""

    __tablename__ = "movimiento_insumo"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    insumo_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("insumo.id"))
    cantidad: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    motivo: Mapped[str] = mapped_column(Text)
    costo_unit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    gasto_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("gasto.id"))
    procedimiento_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("procedimiento.id", ondelete="SET NULL")
    )
    nota: Mapped[str | None] = mapped_column(Text)
    usuario_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    ocurrido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ServicioInsumo(Base):
    """Receta: cuánto de un insumo gasta un servicio cada vez que se ejecuta."""

    __tablename__ = "servicio_insumo"

    servicio_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("servicio.id", ondelete="CASCADE"), primary_key=True
    )
    insumo_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("insumo.id"), primary_key=True)
    cantidad: Mapped[Decimal] = mapped_column(Numeric(12, 3))

    insumo: Mapped[Insumo] = relationship(lazy="joined")
