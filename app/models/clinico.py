"""Agenda y consultas.

La agenda es de F2; estos modelos existen desde F1 porque `odontograma.consulta_id`
apunta a `consulta`, y SQLAlchemy necesita la tabla destino en el metadata para
resolver la clave foránea.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.catalogo import enum_col
from app.models.enums import EstadoCita


class Cita(Base):
    __tablename__ = "cita"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("paciente.id"))
    doctor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("doctor.id"))
    sede_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sede.id"))
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fin: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    motivo: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[EstadoCita] = mapped_column(enum_col(EstadoCita, "estado_cita_t"))
    notas: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Consulta(Base):
    """Una atención concreta, con signos vitales y nota SOAP."""

    __tablename__ = "consulta"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("paciente.id"))
    doctor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("doctor.id"))
    cita_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("cita.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    motivo: Mapped[str | None] = mapped_column(Text)

    presion_sistolica: Mapped[int | None] = mapped_column(Integer)
    presion_diastolica: Mapped[int | None] = mapped_column(Integer)
    pulso: Mapped[int | None] = mapped_column(Integer)
    temperatura: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))

    subjetivo: Mapped[str | None] = mapped_column(Text)
    objetivo: Mapped[str | None] = mapped_column(Text)
    diagnostico: Mapped[str | None] = mapped_column(Text)
    plan: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cita: Mapped[Cita | None] = relationship(lazy="joined")
