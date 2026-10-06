"""Implantes: trazabilidad de por vida."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.catalogo import enum_col
from app.models.enums import EstadoImplante
from app.models.organizacion import Doctor


class SistemaImplante(Base):
    __tablename__ = "sistema_implante"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    marca: Mapped[str] = mapped_column(Text)
    linea: Mapped[str] = mapped_column(Text)
    conexion: Mapped[str | None] = mapped_column(Text)
    proveedor: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class ImplanteEvento(Base):
    """Un hito del seguimiento: colocación, control, segunda fase, carga…"""

    __tablename__ = "implante_evento"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    implante_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("implante.id", ondelete="CASCADE")
    )
    fecha: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    tipo: Mapped[str] = mapped_column(Text)
    doctor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("doctor.id"))
    isq: Mapped[int | None] = mapped_column(SmallInteger)
    hallazgos: Mapped[str | None] = mapped_column(Text)
    notas: Mapped[str | None] = mapped_column(Text)


class Implante(Base):
    """Un implante colocado. `lote` es obligatorio: es lo que permite responder
    a un retiro de producto del fabricante."""

    __tablename__ = "implante"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("paciente.id"))
    doctor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("doctor.id"))
    procedimiento_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("procedimiento.id"))
    sistema_implante_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sistema_implante.id"))
    codigo_fdi: Mapped[int] = mapped_column(SmallInteger, ForeignKey("diente.codigo_fdi"))
    referencia: Mapped[str | None] = mapped_column(Text)
    lote: Mapped[str] = mapped_column(Text)
    serie: Mapped[str | None] = mapped_column(Text)
    diametro_mm: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    longitud_mm: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    plataforma: Mapped[str | None] = mapped_column(Text)
    torque_ncm: Mapped[int | None] = mapped_column(SmallInteger)
    isq: Mapped[int | None] = mapped_column(SmallInteger)
    injerto_oseo: Mapped[bool | None] = mapped_column(Boolean, default=False)
    material_injerto: Mapped[str | None] = mapped_column(Text)
    membrana: Mapped[bool | None] = mapped_column(Boolean, default=False)
    fecha_colocacion: Mapped[date | None] = mapped_column(Date)
    fecha_carga: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[EstadoImplante] = mapped_column(
        enum_col(EstadoImplante, "estado_implante_t"), default=EstadoImplante.PLANIFICADO
    )
    garantia_hasta: Mapped[date | None] = mapped_column(Date)
    notas: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sistema: Mapped[SistemaImplante] = relationship(lazy="joined")
    doctor: Mapped[Doctor] = relationship(lazy="joined")
    eventos: Mapped[list[ImplanteEvento]] = relationship(
        cascade="all, delete-orphan", order_by=(ImplanteEvento.fecha, ImplanteEvento.id)
    )

    @property
    def sistema_nombre(self) -> str:
        return f"{self.sistema.marca} {self.sistema.linea}"

    @property
    def doctor_nombre(self) -> str:
        return self.doctor.nombre_completo
