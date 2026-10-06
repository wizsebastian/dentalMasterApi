"""Archivos del almacén y los que cuelgan del expediente."""

from datetime import date, datetime

from sqlalchemy import CHAR, BigInteger, Date, DateTime, ForeignKey, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Archivo(Base):
    """Un archivo guardado. Su ruta en disco se deriva del `sha256`."""

    __tablename__ = "archivo"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sha256: Mapped[str] = mapped_column(CHAR(64))
    nombre_original: Mapped[str] = mapped_column(Text)
    mime: Mapped[str] = mapped_column(Text)
    bytes: Mapped[int] = mapped_column(BigInteger)
    subido_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentoClinico(Base):
    """Foto, radiografía o examen del paciente.

    Con `consulta_id` es una foto de esa visita. `url` sólo se usa para
    referencias externas; lo que se sube desde la aplicación lleva `archivo_id`.
    """

    __tablename__ = "documento_clinico"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("paciente.id"))
    consulta_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("consulta.id"))
    tipo: Mapped[str] = mapped_column(Text)
    codigo_fdi: Mapped[int | None] = mapped_column(SmallInteger, ForeignKey("diente.codigo_fdi"))
    titulo: Mapped[str | None] = mapped_column(Text)
    archivo_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("archivo.id"))
    url: Mapped[str | None] = mapped_column(Text)
    mime: Mapped[str | None] = mapped_column(Text)
    tomado_en: Mapped[date | None] = mapped_column(Date)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    archivo: Mapped[Archivo | None] = relationship(lazy="joined")
