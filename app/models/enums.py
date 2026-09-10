"""Espejo Python de los 13 ENUM de PostgreSQL.

Los valores deben coincidir exactamente con `01_schema.sql`: SQLAlchemy los
envía como literales al tipo ENUM de la base.
"""

from enum import StrEnum


class Sexo(StrEnum):
    M = "M"
    F = "F"
    O = "O"  # noqa: E741 — el valor lo fija el ENUM sexo_t


class Denticion(StrEnum):
    PERMANENTE = "permanente"
    TEMPORAL = "temporal"


class Arcada(StrEnum):
    SUPERIOR = "superior"
    INFERIOR = "inferior"


class Lado(StrEnum):
    DERECHO = "derecho"
    IZQUIERDO = "izquierdo"


class GrupoDental(StrEnum):
    INCISIVO = "incisivo"
    CANINO = "canino"
    PREMOLAR = "premolar"
    MOLAR = "molar"

    @property
    def es_anterior(self) -> bool:
        """Anteriores llevan cara incisal (I); posteriores, oclusal (O)."""
        return self in (GrupoDental.INCISIVO, GrupoDental.CANINO)


class AmbitoCondicion(StrEnum):
    SUPERFICIE = "superficie"
    DIENTE = "diente"
    RAIZ = "raiz"
    PERIODONTAL = "periodontal"
    PROTESICO = "protesico"


class EstadoHallazgo(StrEnum):
    EXISTENTE = "existente"
    PLANIFICADO = "planificado"
    EN_PROCESO = "en_proceso"
    COMPLETADO = "completado"
    ANULADO = "anulado"


class EstadoCita(StrEnum):
    AGENDADA = "agendada"
    CONFIRMADA = "confirmada"
    EN_SALA = "en_sala"
    ATENDIDA = "atendida"
    CANCELADA = "cancelada"
    NO_ASISTIO = "no_asistio"


class EstadoPlan(StrEnum):
    BORRADOR = "borrador"
    PRESENTADO = "presentado"
    ACEPTADO = "aceptado"
    RECHAZADO = "rechazado"
    EN_EJECUCION = "en_ejecucion"
    FINALIZADO = "finalizado"


class EstadoProcedimiento(StrEnum):
    PENDIENTE = "pendiente"
    EN_PROCESO = "en_proceso"
    COMPLETADO = "completado"
    ANULADO = "anulado"


class EstadoImplante(StrEnum):
    PLANIFICADO = "planificado"
    COLOCADO = "colocado"
    OSEOINTEGRADO = "oseointegrado"
    CARGADO = "cargado"
    FALLIDO = "fallido"
    EXPLANTADO = "explantado"


class EstadoFactura(StrEnum):
    BORRADOR = "borrador"
    EMITIDA = "emitida"
    PARCIAL = "parcial"
    PAGADA = "pagada"
    ANULADA = "anulada"


class RolUsuario(StrEnum):
    ADMIN = "admin"
    DOCTOR = "doctor"
    ASISTENTE = "asistente"
    RECEPCION = "recepcion"
    FACTURACION = "facturacion"
