"""Pacientes, contactos, seguros y ficha médica."""

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core import tiempo
from app.models.base import Base
from app.models.catalogo import Alergia, CondicionMedica, enum_col
from app.models.enums import Sexo
from app.models.organizacion import Doctor


class Paciente(Base):
    __tablename__ = "paciente"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, unique=True)  # expediente PAC-2026-0001
    documento: Mapped[str | None] = mapped_column(Text, unique=True)
    nombres: Mapped[str] = mapped_column(Text)
    apellidos: Mapped[str] = mapped_column(Text)
    # Opcionales: el alta rápida sólo pide nombre, y el resto se completa después.
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date)
    sexo: Mapped[Sexo | None] = mapped_column(enum_col(Sexo, "sexo_t"))
    telefono: Mapped[str | None] = mapped_column(Text)
    celular: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    direccion: Mapped[str | None] = mapped_column(Text)
    ciudad: Mapped[str | None] = mapped_column(Text)
    ocupacion: Mapped[str | None] = mapped_column(Text)
    estado_civil: Mapped[str | None] = mapped_column(Text)
    tipo_sangre: Mapped[str | None] = mapped_column(Text)
    referido_por: Mapped[str | None] = mapped_column(Text)
    sede_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sede.id"))
    doctor_tratante_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("doctor.id"))
    notas: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    contactos: Mapped[list["PacienteContacto"]] = relationship(
        cascade="all, delete-orphan", back_populates="paciente"
    )
    ficha: Mapped["FichaMedica | None"] = relationship(
        cascade="all, delete-orphan", back_populates="paciente"
    )
    doctor_tratante: Mapped[Doctor | None] = relationship(lazy="joined")

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombres} {self.apellidos}"

    @property
    def doctor_tratante_nombre(self) -> str | None:
        return self.doctor_tratante.nombre_completo if self.doctor_tratante else None

    @property
    def edad(self) -> int | None:
        """Edad en años cumplidos a día de hoy; None si no se conoce el nacimiento."""
        if self.fecha_nacimiento is None:
            return None
        hoy = tiempo.hoy()
        cumplido = (hoy.month, hoy.day) >= (
            self.fecha_nacimiento.month,
            self.fecha_nacimiento.day,
        )
        return hoy.year - self.fecha_nacimiento.year - (0 if cumplido else 1)


class PacienteContacto(Base):
    __tablename__ = "paciente_contacto"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("paciente.id", ondelete="CASCADE")
    )
    nombre: Mapped[str] = mapped_column(Text)
    parentesco: Mapped[str | None] = mapped_column(Text)
    telefono: Mapped[str] = mapped_column(Text)
    es_emergencia: Mapped[bool] = mapped_column(Boolean, default=True)
    es_tutor: Mapped[bool] = mapped_column(Boolean, default=False)

    paciente: Mapped[Paciente] = relationship(back_populates="contactos")


class FichaCondicion(Base):
    """Antecedente sistémico del paciente. PK compuesta, sin id propio."""

    __tablename__ = "ficha_condicion"

    ficha_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ficha_medica.id", ondelete="CASCADE"), primary_key=True
    )
    condicion_medica_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("condicion_medica.id"), primary_key=True
    )
    diagnosticado_en: Mapped[date | None] = mapped_column(Date)
    controlado: Mapped[bool | None] = mapped_column(Boolean, default=True)
    detalle: Mapped[str | None] = mapped_column(Text)

    condicion: Mapped[CondicionMedica] = relationship(lazy="joined")

    @property
    def codigo(self) -> str:
        return self.condicion.codigo

    @property
    def nombre(self) -> str:
        return self.condicion.nombre

    @property
    def riesgo(self) -> str | None:
        return self.condicion.riesgo

    @property
    def alerta(self) -> str | None:
        return self.condicion.alerta


class FichaAlergia(Base):
    __tablename__ = "ficha_alergia"

    ficha_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ficha_medica.id", ondelete="CASCADE"), primary_key=True
    )
    alergia_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("alergia.id"), primary_key=True)
    severidad: Mapped[str | None] = mapped_column(Text)  # leve | moderada | severa
    reaccion: Mapped[str | None] = mapped_column(Text)

    alergia: Mapped[Alergia] = relationship(lazy="joined")

    @property
    def codigo(self) -> str:
        return self.alergia.codigo

    @property
    def nombre(self) -> str:
        return self.alergia.nombre

    @property
    def tipo(self) -> str | None:
        return self.alergia.tipo


class FichaMedicamento(Base):
    __tablename__ = "ficha_medicamento"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ficha_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ficha_medica.id", ondelete="CASCADE")
    )
    nombre: Mapped[str] = mapped_column(Text)
    dosis: Mapped[str | None] = mapped_column(Text)
    frecuencia: Mapped[str | None] = mapped_column(Text)
    motivo: Mapped[str | None] = mapped_column(Text)
    desde: Mapped[date | None] = mapped_column(Date)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class FichaMedica(Base):
    """Historia clínica del paciente. Uno a uno: `paciente_id` es UNIQUE."""

    __tablename__ = "ficha_medica"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("paciente.id", ondelete="CASCADE"), unique=True
    )
    motivo_consulta: Mapped[str | None] = mapped_column(Text)
    enfermedad_actual: Mapped[str | None] = mapped_column(Text)
    antecedentes_familiares: Mapped[str | None] = mapped_column(Text)

    # Hábitos
    fuma: Mapped[bool | None] = mapped_column(Boolean, default=False)
    cigarrillos_dia: Mapped[int | None] = mapped_column(Integer)
    consume_alcohol: Mapped[bool | None] = mapped_column(Boolean, default=False)
    bruxismo: Mapped[bool | None] = mapped_column(Boolean, default=False)
    onicofagia: Mapped[bool | None] = mapped_column(Boolean, default=False)
    respirador_bucal: Mapped[bool | None] = mapped_column(Boolean, default=False)

    # Antecedentes odontológicos
    ultima_visita_dental: Mapped[date | None] = mapped_column(Date)
    cepillados_dia: Mapped[int | None] = mapped_column(Integer)
    usa_hilo_dental: Mapped[bool | None] = mapped_column(Boolean, default=False)
    sangrado_encias: Mapped[bool | None] = mapped_column(Boolean, default=False)
    sensibilidad: Mapped[bool | None] = mapped_column(Boolean, default=False)
    dolor_atm: Mapped[bool | None] = mapped_column(Boolean, default=False)

    # Estado sistémico. `anticoagulantes` y `bifosfonatos` son campos propios y no
    # condiciones del catálogo porque cambian el protocolo de cirugía e implantes.
    embarazada: Mapped[bool | None] = mapped_column(Boolean, default=False)
    semanas_gestacion: Mapped[int | None] = mapped_column(Integer)
    anticoagulantes: Mapped[bool | None] = mapped_column(Boolean, default=False)
    bifosfonatos: Mapped[bool | None] = mapped_column(Boolean, default=False)

    observaciones: Mapped[str | None] = mapped_column(Text)
    actualizado_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("doctor.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    paciente: Mapped[Paciente] = relationship(back_populates="ficha")
    condiciones: Mapped[list[FichaCondicion]] = relationship(cascade="all, delete-orphan")
    alergias: Mapped[list[FichaAlergia]] = relationship(cascade="all, delete-orphan")
    medicamentos: Mapped[list[FichaMedicamento]] = relationship(cascade="all, delete-orphan")
