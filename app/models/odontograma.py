"""Odontograma: la foto fechada del estado bucal de un paciente.

Cada odontograma es una versión inmutable. Un índice único parcial
(`uq_odontograma_actual`) garantiza que sólo uno tenga `es_actual = TRUE` por
paciente; los anteriores quedan como historial legal.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.catalogo import CondicionDental, Diente, enum_col
from app.models.enums import AmbitoCondicion, Denticion, EstadoHallazgo


class Odontograma(Base):
    __tablename__ = "odontograma"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("paciente.id", ondelete="CASCADE")
    )
    doctor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("doctor.id"))
    consulta_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("consulta.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    denticion: Mapped[Denticion] = mapped_column(enum_col(Denticion, "denticion_t"))
    fecha: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    es_actual: Mapped[bool] = mapped_column(Boolean, default=True)
    observaciones: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dientes: Mapped[list["OdontogramaDiente"]] = relationship(
        cascade="all, delete-orphan", back_populates="odontograma"
    )
    hallazgos: Mapped[list["OdontogramaHallazgo"]] = relationship(
        cascade="all, delete-orphan", back_populates="odontograma"
    )


class OdontogramaDiente(Base):
    """Estado global de una pieza: presencia, movilidad, sondaje, sangrado.

    Lo que aplica al diente entero, no a una cara concreta.
    """

    __tablename__ = "odontograma_diente"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    odontograma_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("odontograma.id", ondelete="CASCADE")
    )
    codigo_fdi: Mapped[int] = mapped_column(SmallInteger, ForeignKey("diente.codigo_fdi"))
    presente: Mapped[bool] = mapped_column(Boolean, default=True)
    movilidad: Mapped[int | None] = mapped_column(SmallInteger)
    recesion_mm: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    sondaje_mm: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    sangrado: Mapped[bool | None] = mapped_column(Boolean, default=False)
    notas: Mapped[str | None] = mapped_column(Text)

    odontograma: Mapped[Odontograma] = relationship(back_populates="dientes")


class OdontogramaHallazgo(Base):
    """Un hallazgo sobre una pieza, opcionalmente sobre una cara concreta.

    `superficie IS NULL` significa "toda la pieza" —ausente, corona, implante—,
    no un dato que falte. Con un código de cara ('O', 'M'...) el hallazgo es de
    esa superficie: caries, resina.
    """

    __tablename__ = "odontograma_hallazgo"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    odontograma_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("odontograma.id", ondelete="CASCADE")
    )
    codigo_fdi: Mapped[int] = mapped_column(SmallInteger, ForeignKey("diente.codigo_fdi"))
    superficie: Mapped[str | None] = mapped_column(CHAR(1), ForeignKey("superficie.codigo"))
    condicion_dental_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("condicion_dental.id"))
    estado: Mapped[EstadoHallazgo] = mapped_column(enum_col(EstadoHallazgo, "estado_hallazgo_t"))
    doctor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("doctor.id"))
    fecha: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    notas: Mapped[str | None] = mapped_column(Text)

    odontograma: Mapped[Odontograma] = relationship(back_populates="hallazgos")
    condicion: Mapped[CondicionDental] = relationship(lazy="joined")
    diente: Mapped[Diente] = relationship(lazy="joined")

    # El frontend pinta la pieza con estos datos, así que viajan aplanados en el
    # hallazgo en lugar de obligarle a cruzarlos contra el catálogo.
    @property
    def condicion_codigo(self) -> str:
        return self.condicion.codigo

    @property
    def condicion_nombre(self) -> str:
        return self.condicion.nombre

    @property
    def color_hex(self) -> str:
        return self.condicion.color_hex

    @property
    def ambito(self) -> AmbitoCondicion:
        return self.condicion.ambito
