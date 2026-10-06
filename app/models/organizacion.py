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
    Integer,
    Numeric,
    Text,
    func,
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
    whatsapp: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    web: Mapped[str | None] = mapped_column(Text)
    rnc: Mapped[str | None] = mapped_column(Text)
    logo_archivo_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("archivo.id"))
    onboarding_cerrado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    catalogo_revisado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Especialidad(Base):
    __tablename__ = "especialidad"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, unique=True)
    nombre: Mapped[str] = mapped_column(Text)
    descripcion: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class UnidadDental(Base):
    """Un sillón. Es un recurso de la agenda: la base impide ocuparlo dos veces."""

    __tablename__ = "unidad_dental"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sede_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sede.id"))
    nombre: Mapped[str] = mapped_column(Text)
    alquilada: Mapped[bool] = mapped_column(Boolean, default=False)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Correlativo(Base):
    """Último número emitido de cada serie (expedientes, planes, recibos).

    No se escribe desde el ORM: lo avanza `services/correlativos.py` con un
    INSERT … ON CONFLICT que bloquea la fila hasta el fin de la transacción.
    """

    __tablename__ = "correlativo"

    clave: Mapped[str] = mapped_column(Text, primary_key=True)
    ultimo: Mapped[int] = mapped_column(BigInteger, default=0)


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
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

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
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    doctor: Mapped[Doctor | None] = relationship(lazy="joined")
