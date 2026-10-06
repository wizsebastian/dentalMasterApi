"""Catálogo dental: piezas FDI, superficies y condiciones del odontograma.

Datos maestros que carga `02_seed_catalogos.sql`. Son de solo lectura desde la
aplicación: alimentan el odontograma y no se editan en runtime.
"""

from sqlalchemy import CHAR, BigInteger, Boolean, Enum, Integer, SmallInteger, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import AmbitoCondicion, Arcada, Denticion, GrupoDental, Lado


def enum_col(tipo: type, nombre: str) -> Enum:
    """ENUM de PostgreSQL con los valores literales del esquema, no los nombres."""
    return Enum(tipo, name=nombre, values_callable=lambda e: [m.value for m in e])


class Diente(Base):
    """Una pieza dental. La PK es el código FDI (11–48 y 51–85), no un serial."""

    __tablename__ = "diente"

    codigo_fdi: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    cuadrante: Mapped[int] = mapped_column(SmallInteger)
    posicion: Mapped[int] = mapped_column(SmallInteger)
    denticion: Mapped[Denticion] = mapped_column(enum_col(Denticion, "denticion_t"))
    nombre: Mapped[str] = mapped_column(Text)
    grupo: Mapped[GrupoDental] = mapped_column(enum_col(GrupoDental, "grupo_dental_t"))
    arcada: Mapped[Arcada] = mapped_column(enum_col(Arcada, "arcada_t"))
    lado: Mapped[Lado] = mapped_column(enum_col(Lado, "lado_t"))
    universal: Mapped[int | None] = mapped_column(SmallInteger)
    palmer: Mapped[str | None] = mapped_column(Text)

    @property
    def centro_oclusal(self) -> str:
        """Cara central de la pieza: incisal en anteriores, oclusal en posteriores.

        El frontend la necesita para saber si el centro del diente se etiqueta
        'I' u 'O' al dibujar las cinco caras.
        """
        return "I" if self.grupo.es_anterior else "O"


class Superficie(Base):
    """Cara del diente: M, D, V, L, O, I."""

    __tablename__ = "superficie"

    codigo: Mapped[str] = mapped_column(CHAR(1), primary_key=True)
    nombre: Mapped[str] = mapped_column(Text)
    aplica_a: Mapped[str] = mapped_column(Text)  # 'todos' | 'anterior' | 'posterior'


class CondicionDental(Base):
    """Hallazgo o tratamiento que puede registrarse en el odontograma.

    `color_hex` es la única fuente del color con que se pinta la pieza: el
    frontend nunca lo escribe a mano.
    """

    __tablename__ = "condicion_dental"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, unique=True)
    nombre: Mapped[str] = mapped_column(Text)
    ambito: Mapped[AmbitoCondicion] = mapped_column(enum_col(AmbitoCondicion, "ambito_condicion_t"))
    color_hex: Mapped[str] = mapped_column(Text)
    patologico: Mapped[bool] = mapped_column(Boolean)
    orden: Mapped[int | None] = mapped_column(Integer)


class CondicionMedica(Base):
    """Catálogo de antecedentes sistémicos, con su nivel de riesgo y alerta."""

    __tablename__ = "condicion_medica"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, unique=True)
    nombre: Mapped[str] = mapped_column(Text)
    riesgo: Mapped[str | None] = mapped_column(Text)  # bajo | medio | alto
    alerta: Mapped[str | None] = mapped_column(Text)


class Alergia(Base):
    __tablename__ = "alergia"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, unique=True)
    nombre: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str | None] = mapped_column(Text)
    # Nombres que delatan la alergia en una receta: «amoxicilina» para la penicilina.
    palabras_clave: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
