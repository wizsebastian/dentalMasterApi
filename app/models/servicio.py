"""Catálogo de servicios y sus precios.

El precio no vive en `servicio`: cada `lista_precio` (particular o de una
aseguradora) fija el suyo en `precio_servicio`, con vigencia por fechas para no
tocar el histórico.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import CHAR, BigInteger, Boolean, Date, ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.catalogo import CondicionDental


class Aseguradora(Base):
    __tablename__ = "aseguradora"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, unique=True)
    nombre: Mapped[str] = mapped_column(Text)
    telefono: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class PacienteSeguro(Base):
    """Póliza del paciente con una aseguradora (ARS)."""

    __tablename__ = "paciente_seguro"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("paciente.id", ondelete="CASCADE")
    )
    aseguradora_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("aseguradora.id"))
    poliza: Mapped[str] = mapped_column(Text)
    plan: Mapped[str | None] = mapped_column(Text)
    titular: Mapped[str | None] = mapped_column(Text)
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    principal: Mapped[bool] = mapped_column(Boolean, default=True)

    aseguradora: Mapped[Aseguradora] = relationship(lazy="joined")

    @property
    def aseguradora_nombre(self) -> str:
        return self.aseguradora.nombre


class CategoriaServicio(Base):
    __tablename__ = "categoria_servicio"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, unique=True)
    nombre: Mapped[str] = mapped_column(Text)
    orden: Mapped[int | None] = mapped_column(Integer, default=0)


class ListaPrecio(Base):
    """Tarifa. `aseguradora_id IS NULL` es la tarifa particular."""

    __tablename__ = "lista_precio"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, unique=True)
    nombre: Mapped[str] = mapped_column(Text)
    moneda: Mapped[str] = mapped_column(CHAR(3), default="DOP")
    aseguradora_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("aseguradora.id"))
    vigente_desde: Mapped[date] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class PrecioServicio(Base):
    __tablename__ = "precio_servicio"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lista_precio_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("lista_precio.id", ondelete="CASCADE")
    )
    servicio_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("servicio.id"))
    precio: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    costo: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), default=0)
    cobertura_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), default=0)
    tasa_impuesto: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)


class Servicio(Base):
    """Lo que la clínica ofrece y cobra.

    `condicion_resultante_id` dice qué condición pintar en el odontograma cuando
    el servicio se ejecuta sobre una pieza: es lo que permite que lo hecho y lo
    dibujado no discrepen.
    """

    __tablename__ = "servicio"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    categoria_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("categoria_servicio.id"))
    codigo: Mapped[str] = mapped_column(Text, unique=True)
    nombre: Mapped[str] = mapped_column(Text)
    descripcion: Mapped[str | None] = mapped_column(Text)
    requiere_diente: Mapped[bool] = mapped_column(Boolean, default=False)
    requiere_superficie: Mapped[bool] = mapped_column(Boolean, default=False)
    es_implante: Mapped[bool] = mapped_column(Boolean, default=False)
    duracion_min: Mapped[int | None] = mapped_column(Integer, default=30)
    sesiones: Mapped[int | None] = mapped_column(Integer, default=1)
    condicion_resultante_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("condicion_dental.id")
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    categoria: Mapped[CategoriaServicio] = relationship(lazy="joined")
    condicion_resultante: Mapped[CondicionDental | None] = relationship(lazy="joined")
    # La FK de la base no cascada desde servicio: es el ORM quien borra los
    # precios antes que el servicio.
    precios: Mapped[list[PrecioServicio]] = relationship(
        order_by=PrecioServicio.lista_precio_id, cascade="all, delete-orphan"
    )

    @property
    def categoria_nombre(self) -> str:
        return self.categoria.nombre
