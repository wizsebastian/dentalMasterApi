"""Plantillas, documentos emitidos, firmas y recetas."""

from datetime import date, datetime

from sqlalchemy import CHAR, BigInteger, Boolean, Date, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PlantillaDocumento(Base):
    """Texto base de un documento, con variables `{{paciente.nombre}}`."""

    __tablename__ = "plantilla_documento"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, unique=True)
    tipo: Mapped[str] = mapped_column(Text)
    titulo: Mapped[str] = mapped_column(Text)
    cuerpo: Mapped[str] = mapped_column(Text)
    especialidad_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("especialidad.id"))
    requiere_firma: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Firma(Base):
    """Firma manuscrita. `hash_documento` ata el trazo al texto exacto que se firmó."""

    __tablename__ = "firma"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    documento_emitido_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documento_emitido.id", ondelete="CASCADE")
    )
    firmante_nombre: Mapped[str] = mapped_column(Text)
    firmante_rol: Mapped[str] = mapped_column(Text)
    firmante_documento: Mapped[str | None] = mapped_column(Text)
    trazo: Mapped[list] = mapped_column(JSONB)
    hash_documento: Mapped[str] = mapped_column(CHAR(64))
    firmado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dispositivo: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)


class DocumentoEmitido(Base):
    """Un documento ya entregado. Inmutable: se anula y se emite otro, no se edita."""

    __tablename__ = "documento_emitido"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("paciente.id"))
    tipo: Mapped[str] = mapped_column(Text)
    plantilla_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("plantilla_documento.id")
    )
    titulo: Mapped[str] = mapped_column(Text)
    cuerpo: Mapped[str] = mapped_column(Text)
    consulta_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("consulta.id"))
    plan_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("plan_tratamiento.id"))
    doctor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("doctor.id"))
    requiere_firma: Mapped[bool] = mapped_column(Boolean, default=False)
    sha256: Mapped[str] = mapped_column(CHAR(64))
    emitido_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    emitido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_anulacion: Mapped[str | None] = mapped_column(Text)

    firmas: Mapped[list[Firma]] = relationship(cascade="all, delete-orphan", order_by=Firma.id)


class PrescripcionItem(Base):
    __tablename__ = "prescripcion_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    prescripcion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("prescripcion.id", ondelete="CASCADE")
    )
    medicamento: Mapped[str] = mapped_column(Text)
    presentacion: Mapped[str | None] = mapped_column(Text)
    dosis: Mapped[str] = mapped_column(Text)
    frecuencia: Mapped[str] = mapped_column(Text)
    duracion: Mapped[str | None] = mapped_column(Text)


class Prescripcion(Base):
    """Receta. Estructurada: un renglón por medicamento."""

    __tablename__ = "prescripcion"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("paciente.id"))
    doctor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("doctor.id"))
    consulta_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("consulta.id"))
    fecha: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    indicaciones: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list[PrescripcionItem]] = relationship(
        cascade="all, delete-orphan", order_by=PrescripcionItem.id
    )
    doctor: Mapped["Doctor"] = relationship(lazy="joined")  # noqa: F821

    @property
    def doctor_nombre(self) -> str:
        return self.doctor.nombre_completo
