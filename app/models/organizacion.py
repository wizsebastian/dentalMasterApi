"""Sedes, doctores, especialidades y usuarios del sistema."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import RolUsuario


class Sede(Base):
    __tablename__ = "sede"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(Text)
    direccion: Mapped[str | None] = mapped_column(Text)
    ciudad: Mapped[str | None] = mapped_column(Text)
    telefono: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    rnc: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Especialidad(Base):
    __tablename__ = "especialidad"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, unique=True)
    nombre: Mapped[str] = mapped_column(Text)
    descripcion: Mapped[str | None] = mapped_column(Text)


class DoctorEspecialidad(Base):
    __tablename__ = "doctor_especialidad"

    doctor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("doctor.id", ondelete="CASCADE"), primary_key=True
    )
    especialidad_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("especialidad.id"), primary_key=True
    )
    principal: Mapped[bool] = mapped_column(Boolean, default=False)

    especialidad: Mapped[Especialidad] = relationship(lazy="joined")


class Doctor(Base):
    __tablename__ = "doctor"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sede_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sede.id"))
    documento: Mapped[str] = mapped_column(Text, unique=True)
    nombres: Mapped[str] = mapped_column(Text)
    apellidos: Mapped[str] = mapped_column(Text)
    licencia: Mapped[str | None] = mapped_column(Text, unique=True)
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    telefono: Mapped[str | None] = mapped_column(Text)
    fecha_ingreso: Mapped[date | None] = mapped_column(Date)
    porcentaje_comision: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    sede: Mapped[Sede | None] = relationship(lazy="joined")
    especialidades: Mapped[list[DoctorEspecialidad]] = relationship(cascade="all, delete-orphan")

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombres} {self.apellidos}"


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    doctor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("doctor.id"))
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    rol: Mapped[RolUsuario] = mapped_column(
        Enum(RolUsuario, name="rol_usuario_t", values_callable=lambda e: [m.value for m in e])
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    doctor: Mapped[Doctor | None] = relationship(lazy="joined")
