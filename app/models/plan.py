"""Planes de tratamiento y procedimientos.

Plan ≠ procedimiento. `plan_item` es lo cotizado; `procedimiento` es lo
ejecutado, y es el cargo que se le hace al paciente. El enlace `plan_item_id`
es opcional a propósito: no todo lo que se hace estaba en un plan.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.catalogo import enum_col
from app.models.enums import EstadoPlan, EstadoProcedimiento
from app.models.organizacion import Doctor, Especialidad
from app.models.servicio import Servicio


class PlanItem(Base):
    __tablename__ = "plan_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("plan_tratamiento.id", ondelete="CASCADE")
    )
    servicio_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("servicio.id"))
    codigo_fdi: Mapped[int | None] = mapped_column(SmallInteger, ForeignKey("diente.codigo_fdi"))
    superficies: Mapped[str | None] = mapped_column(Text)  # 'MOD', 'OV'…
    cantidad: Mapped[int] = mapped_column(Integer, default=1)
    precio_unit: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    descuento_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    fase: Mapped[int] = mapped_column(Integer, default=1)
    prioridad: Mapped[int] = mapped_column(SmallInteger, default=3)
    aprobado: Mapped[bool] = mapped_column(Boolean, default=False)
    # Generada por la base: nunca se inserta ni se actualiza.
    total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), Computed("cantidad * precio_unit * (1 - descuento_pct/100)")
    )

    servicio: Mapped[Servicio] = relationship(lazy="joined")

    @property
    def servicio_nombre(self) -> str:
        return self.servicio.nombre

    @property
    def servicio_codigo(self) -> str:
        return self.servicio.codigo


class PlanTratamiento(Base):
    """La carpeta clínica: agrupa consultas, se cotiza y se consiente.

    `especialidad_id` es opcional porque un plan puede cruzar especialidades
    (implante más operatoria).
    """

    __tablename__ = "plan_tratamiento"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("paciente.id"))
    doctor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("doctor.id"))
    lista_precio_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("lista_precio.id"))
    especialidad_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("especialidad.id"))
    titulo: Mapped[str | None] = mapped_column(Text)
    codigo: Mapped[str] = mapped_column(Text, unique=True)  # PT-2026-0001
    fecha: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    estado: Mapped[EstadoPlan] = mapped_column(
        enum_col(EstadoPlan, "estado_plan_t"), default=EstadoPlan.BORRADOR
    )
    descuento_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    notas: Mapped[str | None] = mapped_column(Text)
    cerrado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list[PlanItem]] = relationship(
        cascade="all, delete-orphan", order_by=(PlanItem.fase, PlanItem.prioridad, PlanItem.id)
    )
    doctor: Mapped[Doctor] = relationship(lazy="joined")
    especialidad: Mapped[Especialidad | None] = relationship(lazy="joined")

    @property
    def doctor_nombre(self) -> str:
        return self.doctor.nombre_completo

    @property
    def especialidad_nombre(self) -> str | None:
        return self.especialidad.nombre if self.especialidad else None

    @property
    def siguientes(self) -> tuple[EstadoPlan, ...]:
        return self.estado.siguientes


class Procedimiento(Base):
    """Una línea ejecutada dentro de una consulta. `total` es lo que se cobra."""

    __tablename__ = "procedimiento"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("paciente.id"))
    doctor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("doctor.id"))
    servicio_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("servicio.id"))
    consulta_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("consulta.id"))
    plan_item_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("plan_item.id"))
    codigo_fdi: Mapped[int | None] = mapped_column(SmallInteger, ForeignKey("diente.codigo_fdi"))
    superficies: Mapped[str | None] = mapped_column(Text)
    fecha: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    estado: Mapped[EstadoProcedimiento] = mapped_column(
        enum_col(EstadoProcedimiento, "estado_proc_t"), default=EstadoProcedimiento.COMPLETADO
    )
    anestesia: Mapped[str | None] = mapped_column(Text)
    materiales: Mapped[str | None] = mapped_column(Text)
    cantidad: Mapped[int] = mapped_column(Integer, default=1)
    precio: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)  # unitario
    descuento_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    # Generada por la base, como plan_item.total.
    total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), Computed("ROUND(cantidad * precio * (1 - descuento_pct/100), 2)")
    )
    notas: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    servicio: Mapped[Servicio] = relationship(lazy="joined")
    # Sólo lectura: el implante se registra por su propio endpoint.
    implantes: Mapped[list["Implante"]] = relationship(lazy="selectin", viewonly=True)  # noqa: F821

    @property
    def servicio_nombre(self) -> str:
        return self.servicio.nombre

    @property
    def servicio_codigo(self) -> str:
        return self.servicio.codigo

    @property
    def es_implante(self) -> bool:
        return self.servicio.es_implante

    @property
    def implante_id(self) -> int | None:
        """El implante registrado para esta línea, si ya se anotó su lote."""
        return self.implantes[0].id if self.implantes else None
