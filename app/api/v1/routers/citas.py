"""Agenda: citas, sus cambios de estado y su rastro."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import BD, UsuarioAuth, requiere_rol
from app.models.clinico import Cita
from app.models.enums import EstadoCita, RolUsuario
from app.models.organizacion import Usuario
from app.schemas.agenda import CambioEstado, CitaActualizar, CitaCrear, CitaDetalle, CitaLeer
from app.services import agenda

router = APIRouter(prefix="/citas", tags=["agenda"])

PuedeAgendar = Annotated[
    Usuario,
    Depends(requiere_rol(RolUsuario.DOCTOR, RolUsuario.ASISTENTE, RolUsuario.RECEPCION)),
]

# Un listado sin paciente trae un tramo de calendario, nunca la agenda entera.
MAXIMO_DIAS = 62


@router.get("", response_model=list[CitaLeer])
def listar(
    db: BD,
    _: UsuarioAuth,
    desde: Annotated[datetime | None, Query(description="Inicio del tramo, incluido")] = None,
    hasta: Annotated[datetime | None, Query(description="Fin del tramo, excluido")] = None,
    paciente_id: int | None = None,
    doctor_id: int | None = None,
    unidad_id: int | None = None,
    estado: EstadoCita | None = None,
) -> list[Cita]:
    """Citas de un tramo de calendario, o todas las de un paciente.

    No pagina: la interfaz pide una semana o un mes y lo pinta entero. Para que
    eso sea cierto, sin paciente el tramo es obligatorio y está acotado.
    """
    consulta = select(Cita).options(*agenda.CARGA).order_by(Cita.inicio, Cita.id)

    if paciente_id is None:
        if desde is None or hasta is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Indica desde y hasta, o un paciente"
            )
        if hasta <= desde or hasta - desde > timedelta(days=MAXIMO_DIAS):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"El tramo debe ser positivo y de {MAXIMO_DIAS} días como máximo",
            )
    else:
        consulta = consulta.where(Cita.paciente_id == paciente_id)

    if desde is not None:
        consulta = consulta.where(Cita.fin > desde)
    if hasta is not None:
        consulta = consulta.where(Cita.inicio < hasta)
    if doctor_id is not None:
        consulta = consulta.where(Cita.doctor_id == doctor_id)
    if unidad_id is not None:
        consulta = consulta.where(Cita.unidad_id == unidad_id)
    if estado is not None:
        consulta = consulta.where(Cita.estado == estado)

    return list(db.scalars(consulta))


@router.get("/{cita_id}", response_model=CitaDetalle)
def obtener(cita_id: int, db: BD, _: UsuarioAuth) -> Cita:
    cita = db.scalar(
        select(Cita).where(Cita.id == cita_id).options(*agenda.CARGA, selectinload(Cita.eventos))
    )
    if cita is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La cita no existe")
    return cita


@router.post("", response_model=CitaLeer, status_code=status.HTTP_201_CREATED)
def crear(datos: CitaCrear, db: BD, usuario: PuedeAgendar) -> Cita:
    servicio = agenda.exigir_referencias(
        db,
        paciente_id=datos.paciente_id,
        doctor_id=datos.doctor_id,
        unidad_id=datos.unidad_id,
        servicio_id=datos.servicio_id,
    )
    fin = agenda.calcular_fin(datos.inicio, datos.duracion_min, servicio)
    motivo_sobrecupo = agenda.validar_sobrecupo(datos.sobrecupo, datos.sobrecupo_motivo)

    ocupa = datos.estado not in agenda.LIBERAN
    if ocupa and not datos.sobrecupo:
        agenda.exigir_hueco(
            db, doctor_id=datos.doctor_id, unidad_id=datos.unidad_id, inicio=datos.inicio, fin=fin
        )

    cita = Cita(
        **datos.model_dump(exclude={"duracion_min", "sobrecupo_motivo"}),
        fin=fin,
        sobrecupo_motivo=motivo_sobrecupo,
        creado_por=usuario.id,
    )
    db.add(cita)
    db.flush()
    agenda.registrar_evento(
        db, cita, "creada", usuario.id, inicio_nuevo=cita.inicio, estado_nuevo=cita.estado
    )
    db.commit()
    return agenda.obtener(db, cita.id)


@router.patch("/{cita_id}", response_model=CitaLeer)
def actualizar(cita_id: int, datos: CitaActualizar, db: BD, usuario: PuedeAgendar) -> Cita:
    """Edita la cita. Mover el horario es reprogramar: conserva la cita y deja rastro."""
    cita = agenda.obtener(db, cita_id)
    cambios = datos.model_dump(exclude_unset=True)

    if cita.estado == EstadoCita.ATENDIDA and (
        {"inicio", "duracion_min", "doctor_id", "unidad_id"} & cambios.keys()
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Una cita atendida ya no se puede mover ni reasignar"
        )
    if "doctor_id" in cambios and cambios["doctor_id"] is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "doctor_id: no puede quedar vacío"
        )
    if "inicio" in cambios and cambios["inicio"] is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "inicio: no puede quedar vacío")

    doctor_id = cambios.get("doctor_id", cita.doctor_id)
    unidad_id = cambios.get("unidad_id", cita.unidad_id)
    servicio_id = cambios.get("servicio_id", cita.servicio_id)
    servicio = agenda.exigir_referencias(
        db,
        doctor_id=cambios.get("doctor_id"),
        unidad_id=cambios.get("unidad_id"),
        servicio_id=servicio_id,
    )

    inicio = cambios.get("inicio", cita.inicio)
    if "inicio" in cambios or "duracion_min" in cambios:
        # Al mover sin decir duración se conserva la que la cita ya tenía.
        minutos = cambios.get("duracion_min") or int((cita.fin - cita.inicio).total_seconds() // 60)
        fin = agenda.calcular_fin(inicio, minutos, servicio)
    else:
        fin = cita.fin

    sobrecupo = cambios.get("sobrecupo", cita.sobrecupo)
    if sobrecupo is None:
        sobrecupo = cita.sobrecupo
    motivo_sobrecupo = agenda.validar_sobrecupo(
        sobrecupo, cambios.get("sobrecupo_motivo", cita.sobrecupo_motivo)
    )

    if cita.estado not in agenda.LIBERAN and not sobrecupo:
        agenda.exigir_hueco(
            db, doctor_id=doctor_id, unidad_id=unidad_id, inicio=inicio, fin=fin, excepto=cita.id
        )

    if inicio != cita.inicio or fin != cita.fin:
        agenda.registrar_evento(
            db,
            cita,
            "reprogramada",
            usuario.id,
            inicio_anterior=cita.inicio,
            inicio_nuevo=inicio,
            motivo=(datos.motivo_cambio or "").strip() or None,
        )
        # El recordatorio enviado hablaba del horario viejo.
        cita.recordatorio_enviado_en = None

    cita.doctor_id = doctor_id
    cita.unidad_id = unidad_id
    cita.servicio_id = servicio_id
    cita.inicio = inicio
    cita.fin = fin
    cita.sobrecupo = sobrecupo
    cita.sobrecupo_motivo = motivo_sobrecupo
    for campo in ("motivo", "notas"):
        if campo in cambios:
            setattr(cita, campo, (cambios[campo] or "").strip() or None)

    db.commit()
    return agenda.obtener(db, cita_id)


@router.post("/{cita_id}/estado", response_model=CitaLeer)
def cambiar_estado(cita_id: int, datos: CambioEstado, db: BD, usuario: PuedeAgendar) -> Cita:
    cita = agenda.obtener(db, cita_id)
    agenda.cambiar_estado(db, cita, datos.estado, motivo=datos.motivo, usuario_id=usuario.id)
    db.commit()
    return agenda.obtener(db, cita_id)


@router.post("/{cita_id}/recordatorio", response_model=CitaLeer)
def marcar_recordatorio(cita_id: int, db: BD, usuario: PuedeAgendar) -> Cita:
    """Anota que se envió el recordatorio. El mensaje lo abre la interfaz en WhatsApp."""
    cita = agenda.obtener(db, cita_id)
    cita.recordatorio_enviado_en = datetime.now(UTC)
    agenda.registrar_evento(db, cita, "recordatorio", usuario.id)
    db.commit()
    return agenda.obtener(db, cita_id)
