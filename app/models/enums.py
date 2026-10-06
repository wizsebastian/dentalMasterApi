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

    @property
    def ocupa_agenda(self) -> bool:
        """Falso en los estados que liberan al doctor y al sillón.

        Coincide con el filtro de las restricciones de exclusión de `cita`.
        """
        return self not in (EstadoCita.CANCELADA, EstadoCita.NO_ASISTIO)

    @property
    def siguientes(self) -> tuple["EstadoCita", ...]:
        """A qué estados puede pasar una cita desde éste.

        Una cita atendida no se mueve: ya tiene (o tendrá) una consulta colgando.
        Cancelada y no asistió se pueden reabrir.
        """
        return _TRANSICIONES_CITA[self]


_TRANSICIONES_CITA: dict[EstadoCita, tuple[EstadoCita, ...]] = {
    EstadoCita.AGENDADA: (
        EstadoCita.CONFIRMADA,
        EstadoCita.EN_SALA,
        EstadoCita.ATENDIDA,
        EstadoCita.CANCELADA,
        EstadoCita.NO_ASISTIO,
    ),
    EstadoCita.CONFIRMADA: (
        EstadoCita.EN_SALA,
        EstadoCita.ATENDIDA,
        EstadoCita.CANCELADA,
        EstadoCita.NO_ASISTIO,
        EstadoCita.AGENDADA,
    ),
    EstadoCita.EN_SALA: (EstadoCita.ATENDIDA, EstadoCita.CONFIRMADA, EstadoCita.CANCELADA),
    EstadoCita.ATENDIDA: (),
    EstadoCita.CANCELADA: (EstadoCita.AGENDADA,),
    EstadoCita.NO_ASISTIO: (EstadoCita.AGENDADA,),
}


class EstadoPlan(StrEnum):
    BORRADOR = "borrador"
    PRESENTADO = "presentado"
    ACEPTADO = "aceptado"
    RECHAZADO = "rechazado"
    EN_EJECUCION = "en_ejecucion"
    FINALIZADO = "finalizado"

    @property
    def abierto(self) -> bool:
        """Un plan finalizado o rechazado no admite consultas ni ítems nuevos."""
        return self not in (EstadoPlan.FINALIZADO, EstadoPlan.RECHAZADO)

    @property
    def siguientes(self) -> tuple["EstadoPlan", ...]:
        """A qué estados puede pasar a mano. `en_ejecucion` no está: llega solo
        con la primera línea ejecutada."""
        return _TRANSICIONES_PLAN[self]


_TRANSICIONES_PLAN: dict[EstadoPlan, tuple[EstadoPlan, ...]] = {
    EstadoPlan.BORRADOR: (EstadoPlan.PRESENTADO, EstadoPlan.ACEPTADO),
    EstadoPlan.PRESENTADO: (EstadoPlan.ACEPTADO, EstadoPlan.RECHAZADO, EstadoPlan.BORRADOR),
    EstadoPlan.ACEPTADO: (EstadoPlan.FINALIZADO, EstadoPlan.BORRADOR),
    EstadoPlan.EN_EJECUCION: (EstadoPlan.FINALIZADO,),
    EstadoPlan.RECHAZADO: (EstadoPlan.BORRADOR,),
    EstadoPlan.FINALIZADO: (EstadoPlan.EN_EJECUCION,),
}


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
    """La factura es el comprobante fiscal: no recibe pagos, así que no tiene
    estados de cobro. Lo cobrado vive en `pago` y `pago_aplicacion`."""

    BORRADOR = "borrador"
    EMITIDA = "emitida"
    ANULADA = "anulada"


class RolUsuario(StrEnum):
    ADMIN = "admin"
    DOCTOR = "doctor"
    ASISTENTE = "asistente"
    RECEPCION = "recepcion"
    FACTURACION = "facturacion"
