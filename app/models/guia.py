"""Guía interactiva: lo que quien prueba el sistema marca y escribe en `/guia`."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class GuiaSesion(Base):
    __tablename__ = "guia_sesion"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, unique=True)
    nombre: Mapped[str] = mapped_column(Text)
    rol: Mapped[str | None] = mapped_column(Text)
    impresion_general: Mapped[str] = mapped_column(Text, default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ip: Mapped[str | None] = mapped_column(INET)
    dispositivo: Mapped[str | None] = mapped_column(Text)

    respuestas: Mapped[list["GuiaRespuesta"]] = relationship(
        back_populates="sesion", order_by="GuiaRespuesta.paso_id"
    )


class GuiaRespuesta(Base):
    __tablename__ = "guia_respuesta"

    sesion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guia_sesion.id", ondelete="CASCADE"), primary_key=True
    )
    paso_id: Mapped[str] = mapped_column(Text, primary_key=True)
    estado: Mapped[str] = mapped_column(Text, default="")
    nota: Mapped[str] = mapped_column(Text, default="")
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sesion: Mapped[GuiaSesion] = relationship(back_populates="respuestas")


class GuiaEvento(Base):
    """Bitácora de sólo inserción: cada cambio de estado o de nota."""

    __tablename__ = "guia_evento"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sesion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guia_sesion.id", ondelete="CASCADE")
    )
    paso_id: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(Text)
    nota: Mapped[str] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
