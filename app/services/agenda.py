"""Reglas de la agenda que el esquema no puede expresar con un mensaje útil.

La base ya impide los solapes (`ex_cita_doctor`, `ex_cita_unidad`); aquí se
comprueban antes para poder decir *con qué cita* choca, y se lleva el rastro
de cada cambio en `cita_evento`.
"""

from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.tiempo import local
from app.models.clinico import Cita, CitaEvento
from app.models.enums import EstadoCita
from app.models.organizacion import Doctor, UnidadDental
from app.models.paciente import Paciente
from app.models.servicio import Servicio

DURACION_POR_DEFECTO = 30

# Estados que liberan al doctor y al sillón.
LIBERAN = tuple(e for e in EstadoCita if not e.ocupa_agenda)

CARGA = (
    joinedload(Cita.paciente),
    joinedload(Cita.doctor),
    joinedload(Cita.unidad),
    joinedload(Cita.servicio),
)


def obtener(db: Session, cita_id: int) -> Cita:
    cita = db.scalar(select(Cita).where(Cita.id == cita_id).options(*CARGA))
    if cita is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La cita no existe")
    return cita


def exigir_referencias(
    db: Session,
    *,
    paciente_id: int | None = None,
    doctor_id: int | None = None,
    unidad_id: int | None = None,
    servicio_id: int | None = None,
) -> Servicio | None:
    """Comprueba que lo referenciado existe y está activo. Devuelve el servicio."""
    if paciente_id is not None and db.get(Paciente, paciente_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "paciente_id: no existe")

    if doctor_id is not None:
        doctor = db.get(Doctor, doctor_id)
        if doctor is None or not doctor.activo:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "doctor_id: el doctor no existe o está inactivo",
            )

    if unidad_id is not None:
        unidad = db.get(UnidadDental, unidad_id)
        if unidad is None or not unidad.activo:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "unidad_id: la unidad no existe o está inactiva",
            )

    if servicio_id is None:
        return None
    servicio = db.get(Servicio, servicio_id)
    if servicio is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "servicio_id: no existe")
    return servicio


def calcular_fin(inicio: datetime, duracion_min: int | None, servicio: Servicio | None) -> datetime:
    """La duración pedida manda; si no, la del servicio; si no, 30 minutos."""
    minutos = duracion_min or (servicio.duracion_min if servicio else None) or DURACION_POR_DEFECTO
    return inicio + timedelta(minutes=minutos)


def _hora(momento: datetime) -> str:
    return local(momento).strftime("%H:%M")


def exigir_hueco(
    db: Session,
    *,
    doctor_id: int,
    unidad_id: int | None,
    inicio: datetime,
    fin: datetime,
    excepto: int | None = None,
) -> None:
    """409 si el doctor o el sillón ya están ocupados en ese tramo.

    Dice con qué cita choca: «ya tiene una cita» sin más obliga a ir a buscarla.
    """
    recurso = Cita.doctor_id == doctor_id
    if unidad_id is not None:
        recurso = or_(recurso, Cita.unidad_id == unidad_id)

    consulta = (
        select(Cita)
        .where(
            recurso,
            Cita.estado.not_in(LIBERAN),
            Cita.sobrecupo.is_(False),
            Cita.inicio < fin,
            Cita.fin > inicio,
        )
        .options(joinedload(Cita.paciente), joinedload(Cita.unidad))
        .order_by(Cita.inicio)
    )
    if excepto is not None:
        consulta = consulta.where(Cita.id != excepto)

    choque = db.scalars(consulta).first()
    if choque is None:
        return

    quien = "El doctor" if choque.doctor_id == doctor_id else f"La unidad «{choque.unidad.nombre}»"
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        f"{quien} ya tiene una cita de {_hora(choque.inicio)} a {_hora(choque.fin)} "
        f"con {choque.paciente.nombre_completo}. Elige otro horario o agéndala como sobrecupo.",
    )


def validar_sobrecupo(sobrecupo: bool, motivo: str | None) -> str | None:
    """El sobrecupo es la única vía para solapar a propósito, y exige decir por qué."""
    motivo = (motivo or "").strip() or None
    if sobrecupo and motivo is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "sobrecupo_motivo: explica por qué se solapa"
        )
    return motivo if sobrecupo else None


def registrar_evento(db: Session, cita: Cita, tipo: str, usuario_id: int | None, **datos) -> None:
    db.add(CitaEvento(cita_id=cita.id, tipo=tipo, usuario_id=usuario_id, **datos))


def cambiar_estado(
    db: Session, cita: Cita, nuevo: EstadoCita, *, motivo: str | None, usuario_id: int | None
) -> None:
    if nuevo == cita.estado:
        return
    if nuevo not in cita.estado.siguientes:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Una cita «{cita.estado.value}» no puede pasar a «{nuevo.value}»",
        )

    # Reabrir una cita cancelada vuelve a ocupar el hueco: puede que ya no esté libre.
    if cita.estado in LIBERAN and not cita.sobrecupo:
        exigir_hueco(
            db,
            doctor_id=cita.doctor_id,
            unidad_id=cita.unidad_id,
            inicio=cita.inicio,
            fin=cita.fin,
            excepto=cita.id,
        )

    registrar_evento(
        db,
        cita,
        "estado",
        usuario_id,
        estado_anterior=cita.estado,
        estado_nuevo=nuevo,
        motivo=(motivo or "").strip() or None,
    )
    cita.estado = nuevo
