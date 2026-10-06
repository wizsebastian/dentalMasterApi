"""Agenda y consultas."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.catalogo import enum_col
from app.models.enums import EstadoCita
from app.models.organizacion import Doctor, UnidadDental
from app.models.paciente import Paciente
from app.models.plan import Procedimiento
from app.models.servicio import Servicio


class Cita(Base):
    """Un hueco de agenda.

    Un doctor y un sillón no pueden estar en dos citas vivas a la vez: lo impiden
    las restricciones de exclusión `ex_cita_doctor` y `ex_cita_unidad`. La única
    forma de solapar a propósito es `sobrecupo`, que exige motivo.
    """

    __tablename__ = "cita"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("paciente.id"))
    doctor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("doctor.id"))
    sede_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sede.id"))
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fin: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    unidad_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("unidad_dental.id"))
    servicio_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("servicio.id"))
    plan_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("plan_tratamiento.id"))
    motivo: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[EstadoCita] = mapped_column(
        enum_col(EstadoCita, "estado_cita_t"), default=EstadoCita.AGENDADA
    )
    notas: Mapped[str | None] = mapped_column(Text)
    sobrecupo: Mapped[bool] = mapped_column(Boolean, default=False)
    sobrecupo_motivo: Mapped[str | None] = mapped_column(Text)
    recordatorio_enviado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    eventos: Mapped[list["CitaEvento"]] = relationship(
        cascade="all, delete-orphan", order_by="CitaEvento.ocurrido_en"
    )
    # Sin carga automática: el listado de la agenda las pide con joinedload.
    paciente: Mapped["Paciente"] = relationship()
    doctor: Mapped["Doctor"] = relationship()
    unidad: Mapped["UnidadDental | None"] = relationship()
    servicio: Mapped["Servicio | None"] = relationship()

    # La agenda pinta estos datos en cada bloque: viajan aplanados en la cita.
    @property
    def paciente_nombre(self) -> str:
        return self.paciente.nombre_completo

    @property
    def paciente_celular(self) -> str | None:
        return self.paciente.celular or self.paciente.telefono

    @property
    def doctor_nombre(self) -> str:
        return self.doctor.nombre_completo

    @property
    def unidad_nombre(self) -> str | None:
        return self.unidad.nombre if self.unidad else None

    @property
    def servicio_nombre(self) -> str | None:
        return self.servicio.nombre if self.servicio else None

    @property
    def siguientes(self) -> tuple[EstadoCita, ...]:
        """Estados a los que puede pasar: la interfaz ofrece sólo estos."""
        return self.estado.siguientes


class CitaEvento(Base):
    """Rastro de la cita. Reprogramar conserva la cita y añade un evento."""

    __tablename__ = "cita_evento"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cita_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cita.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(Text)  # creada | reprogramada | estado | recordatorio
    inicio_anterior: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inicio_nuevo: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estado_anterior: Mapped[EstadoCita | None] = mapped_column(
        enum_col(EstadoCita, "estado_cita_t")
    )
    estado_nuevo: Mapped[EstadoCita | None] = mapped_column(enum_col(EstadoCita, "estado_cita_t"))
    motivo: Mapped[str | None] = mapped_column(Text)
    usuario_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    ocurrido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Consulta(Base):
    """Una visita, con signos vitales y nota SOAP.

    `plan_id` la cuelga de un plan de tratamiento; NULL es una consulta suelta.
    La base garantiza con una clave foránea compuesta que el plan sea del mismo
    paciente.
    """

    __tablename__ = "consulta"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("paciente.id"))
    doctor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("doctor.id"))
    cita_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("cita.id"))
    plan_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("plan_tratamiento.id"))
    unidad_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("unidad_dental.id"))
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
    notas: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cita: Mapped[Cita | None] = relationship(lazy="joined")
    doctor: Mapped["Doctor"] = relationship(lazy="joined")
    unidad: Mapped["UnidadDental | None"] = relationship(lazy="joined")
    # Las líneas ejecutadas en la visita: lo que se le cobra al paciente.
    lineas: Mapped[list["Procedimiento"]] = relationship(
        cascade="all, delete-orphan", order_by="Procedimiento.id"
    )

    @property
    def doctor_nombre(self) -> str:
        return self.doctor.nombre_completo

    @property
    def unidad_nombre(self) -> str | None:
        return self.unidad.nombre if self.unidad else None
