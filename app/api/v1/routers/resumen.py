"""El resumen del paciente y sus seguros.

El resumen no se escribe: sale de lo que ya está registrado. Por eso no puede
quedarse viejo ni contradecir al expediente.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.deps import BD, UsuarioAuth, requiere_rol
from app.core.tiempo import hoy, local
from app.models.archivo import DocumentoClinico
from app.models.clinico import Cita, Consulta
from app.models.documento import DocumentoEmitido, Firma
from app.models.enums import EstadoCita, RolUsuario
from app.models.implante import Implante
from app.models.organizacion import Usuario
from app.models.paciente import Paciente
from app.models.plan import PlanTratamiento, Procedimiento
from app.models.servicio import Aseguradora, PacienteSeguro
from app.schemas.resumen import (
    ResumenCita,
    ResumenClinico,
    ResumenConsulta,
    ResumenImplante,
    ResumenPlan,
    SeguroEscribir,
    SeguroLeer,
)

router = APIRouter(tags=["resumen y seguros"])

PuedeEditar = Annotated[
    Usuario,
    Depends(
        requiere_rol(
            RolUsuario.RECEPCION, RolUsuario.FACTURACION, RolUsuario.DOCTOR, RolUsuario.ASISTENTE
        )
    ),
]

CERO = Decimal(0)


def _exigir_paciente(db: Session, paciente_id: int) -> None:
    if db.get(Paciente, paciente_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El paciente no existe")


# --- Seguros -------------------------------------------------------------------


def _seguro_leer(seguro: PacienteSeguro) -> SeguroLeer:
    dia = hoy()
    vigente = (seguro.vigente_desde is None or seguro.vigente_desde <= dia) and (
        seguro.vigente_hasta is None or seguro.vigente_hasta >= dia
    )
    return SeguroLeer.model_validate(seguro).model_copy(update={"vigente": vigente})


def _seguros(db: Session, paciente_id: int) -> list[PacienteSeguro]:
    return list(
        db.scalars(
            select(PacienteSeguro)
            .where(PacienteSeguro.paciente_id == paciente_id)
            .order_by(PacienteSeguro.principal.desc(), PacienteSeguro.id)
        )
    )


def _exigir_aseguradora(db: Session, aseguradora_id: int) -> None:
    if db.get(Aseguradora, aseguradora_id) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "aseguradora_id: la aseguradora no existe"
        )


def _un_solo_principal(db: Session, seguro: PacienteSeguro) -> None:
    if not seguro.principal:
        return
    for otro in _seguros(db, seguro.paciente_id):
        if otro.id != seguro.id:
            otro.principal = False


@router.get("/pacientes/{paciente_id}/seguros", response_model=list[SeguroLeer])
def seguros_del_paciente(paciente_id: int, db: BD, _: UsuarioAuth) -> list[SeguroLeer]:
    _exigir_paciente(db, paciente_id)
    return [_seguro_leer(s) for s in _seguros(db, paciente_id)]


@router.post(
    "/pacientes/{paciente_id}/seguros",
    response_model=SeguroLeer,
    status_code=status.HTTP_201_CREATED,
)
def agregar_seguro(paciente_id: int, datos: SeguroEscribir, db: BD, _: PuedeEditar) -> SeguroLeer:
    _exigir_paciente(db, paciente_id)
    _exigir_aseguradora(db, datos.aseguradora_id)
    seguro = PacienteSeguro(paciente_id=paciente_id, **datos.model_dump())
    db.add(seguro)
    db.flush()
    _un_solo_principal(db, seguro)
    db.commit()
    db.refresh(seguro)
    return _seguro_leer(seguro)


@router.put("/seguros/{seguro_id}", response_model=SeguroLeer)
def actualizar_seguro(seguro_id: int, datos: SeguroEscribir, db: BD, _: PuedeEditar) -> SeguroLeer:
    seguro = db.get(PacienteSeguro, seguro_id)
    if seguro is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El seguro no existe")
    _exigir_aseguradora(db, datos.aseguradora_id)
    for campo, valor in datos.model_dump().items():
        setattr(seguro, campo, valor)
    db.flush()
    _un_solo_principal(db, seguro)
    db.commit()
    db.refresh(seguro)
    return _seguro_leer(seguro)


@router.delete("/seguros/{seguro_id}", status_code=status.HTTP_204_NO_CONTENT)
def quitar_seguro(seguro_id: int, db: BD, _: PuedeEditar) -> Response:
    seguro = db.get(PacienteSeguro, seguro_id)
    if seguro is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El seguro no existe")
    db.delete(seguro)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Resumen -------------------------------------------------------------------

_BALANCE = text("SELECT balance, credito_sin_aplicar FROM v_estado_cuenta WHERE paciente_id = :pid")


def _planes(db: Session, paciente_id: int) -> list[ResumenPlan]:
    planes = db.scalars(
        select(PlanTratamiento)
        .where(PlanTratamiento.paciente_id == paciente_id)
        .options(selectinload(PlanTratamiento.items))
        .order_by(PlanTratamiento.fecha.desc(), PlanTratamiento.id.desc())
    ).all()
    abiertos = [p for p in planes if p.estado.abierto]
    ids = [item.id for plan in abiertos for item in plan.items]
    cumplidos = (
        set(db.scalars(select(Procedimiento.plan_item_id).where(Procedimiento.plan_item_id.in_(ids))))
        if ids
        else set()
    )  # fmt: skip

    resumen = []
    for plan in abiertos:
        factor = 1 - plan.descuento_pct / 100
        pendientes = [item for item in plan.items if item.id not in cumplidos]
        siguiente = pendientes[0] if pendientes else None
        resumen.append(
            ResumenPlan(
                id=plan.id,
                codigo=plan.codigo,
                titulo=plan.titulo,
                estado=plan.estado,
                items=len(plan.items),
                hechos=len(plan.items) - len(pendientes),
                total=(sum((i.total for i in plan.items), CERO) * factor).quantize(Decimal("0.01")),
                pendiente=(sum((i.total for i in pendientes), CERO) * factor).quantize(
                    Decimal("0.01")
                ),
                siguiente=(
                    siguiente.servicio.nombre
                    + (f" · pieza {siguiente.codigo_fdi}" if siguiente.codigo_fdi else "")
                    if siguiente
                    else None
                ),
            )
        )
    return resumen


@router.get("/pacientes/{paciente_id}/resumen", response_model=ResumenClinico)
def resumen_del_paciente(paciente_id: int, db: BD, _: UsuarioAuth) -> ResumenClinico:
    _exigir_paciente(db, paciente_id)

    consultas, primera = db.execute(
        select(func.count(Consulta.id), func.min(Consulta.fecha)).where(
            Consulta.paciente_id == paciente_id
        )
    ).one()
    ultima = db.scalar(
        select(Consulta)
        .where(Consulta.paciente_id == paciente_id)
        .order_by(Consulta.fecha.desc(), Consulta.id.desc())
        .limit(1)
    )
    proxima = db.scalar(
        select(Cita)
        .where(
            Cita.paciente_id == paciente_id,
            Cita.inicio >= datetime.now(UTC),
            Cita.estado.in_([e for e in EstadoCita if e.ocupa_agenda]),
        )
        .options(joinedload(Cita.doctor), joinedload(Cita.servicio))
        .order_by(Cita.inicio)
        .limit(1)
    )
    ausencias = db.scalar(
        select(func.count(Cita.id)).where(
            Cita.paciente_id == paciente_id, Cita.estado == EstadoCita.NO_ASISTIO
        )
    )
    implantes = db.scalars(
        select(Implante)
        .where(Implante.paciente_id == paciente_id)
        .order_by(Implante.codigo_fdi, Implante.id)
    ).unique()
    seguros = _seguros(db, paciente_id)
    cuenta = db.execute(_BALANCE, {"pid": paciente_id}).one_or_none()
    por_firmar = db.scalar(
        select(func.count(DocumentoEmitido.id)).where(
            DocumentoEmitido.paciente_id == paciente_id,
            DocumentoEmitido.requiere_firma,
            DocumentoEmitido.anulado_en.is_(None),
            ~select(Firma.id).where(Firma.documento_emitido_id == DocumentoEmitido.id).exists(),
        )
    )
    archivos = db.scalar(
        select(func.count(DocumentoClinico.id)).where(DocumentoClinico.paciente_id == paciente_id)
    )

    return ResumenClinico(
        paciente_id=paciente_id,
        primera_visita=local(primera).date() if primera else None,
        consultas=consultas,
        ausencias=ausencias or 0,
        ultima_consulta=ResumenConsulta(
            id=ultima.id,
            fecha=ultima.fecha,
            doctor_nombre=ultima.doctor_nombre,
            motivo=ultima.motivo,
            diagnostico=ultima.diagnostico,
            servicios=[linea.servicio.nombre for linea in ultima.lineas],
        )
        if ultima
        else None,
        proxima_cita=ResumenCita(
            id=proxima.id,
            inicio=proxima.inicio,
            doctor_nombre=proxima.doctor_nombre,
            servicio_nombre=proxima.servicio_nombre,
            estado=proxima.estado,
        )
        if proxima
        else None,
        planes=_planes(db, paciente_id),
        implantes=[
            ResumenImplante(
                id=i.id,
                codigo_fdi=i.codigo_fdi,
                sistema_nombre=i.sistema_nombre,
                lote=i.lote,
                estado=i.estado,
                fecha_colocacion=i.fecha_colocacion,
            )
            for i in implantes
        ],
        seguro=_seguro_leer(seguros[0]) if seguros else None,
        balance=cuenta.balance if cuenta else CERO,
        credito_sin_aplicar=cuenta.credito_sin_aplicar if cuenta else CERO,
        por_firmar=por_firmar or 0,
        archivos=archivos or 0,
    )
