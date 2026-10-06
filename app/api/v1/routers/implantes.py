"""Implantes: registro desde la línea de consulta, seguimiento y búsqueda por lote."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import BD, UsuarioAuth, requiere_rol
from app.core.tiempo import hoy
from app.models.catalogo import Diente
from app.models.enums import EstadoImplante, RolUsuario
from app.models.implante import Implante, ImplanteEvento, SistemaImplante
from app.models.organizacion import Doctor, Usuario
from app.models.paciente import Paciente
from app.models.plan import Procedimiento
from app.schemas.implante import (
    EventoCrear,
    ImplanteActualizar,
    ImplanteConPaciente,
    ImplanteCrear,
    ImplanteLeer,
    SistemaCrear,
    SistemaLeer,
)
from app.services.busqueda import coincide

router = APIRouter(tags=["implantes"])

PuedeAtender = Annotated[Usuario, Depends(requiere_rol(RolUsuario.DOCTOR, RolUsuario.ASISTENTE))]

NO_PROCESABLE = status.HTTP_422_UNPROCESSABLE_ENTITY

# El estado en que deja al implante cada hito, si quien lo registra no dice otro.
_ESTADO_TRAS = {
    "colocacion": EstadoImplante.COLOCADO,
    "carga": EstadoImplante.CARGADO,
    "retiro": EstadoImplante.EXPLANTADO,
}


def _implante(db: Session, implante_id: int) -> Implante:
    implante = db.get(Implante, implante_id)
    if implante is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El implante no existe")
    return implante


def _exigir_sistema(db: Session, sistema_id: int) -> None:
    if db.get(SistemaImplante, sistema_id) is None:
        raise HTTPException(NO_PROCESABLE, "sistema_implante_id: el sistema no existe")


def _exigir_doctor(db: Session, doctor_id: int | None) -> None:
    if doctor_id is not None and db.get(Doctor, doctor_id) is None:
        raise HTTPException(NO_PROCESABLE, "doctor_id: el doctor no existe")


# --- Sistemas ------------------------------------------------------------------


@router.get("/sistemas-implante", response_model=list[SistemaLeer])
def listar_sistemas(db: BD, _: UsuarioAuth) -> list[SistemaImplante]:
    return list(
        db.scalars(
            select(SistemaImplante)
            .where(SistemaImplante.activo)
            .order_by(SistemaImplante.marca, SistemaImplante.linea)
        )
    )


@router.post("/sistemas-implante", response_model=SistemaLeer, status_code=status.HTTP_201_CREATED)
def crear_sistema(datos: SistemaCrear, db: BD, _: PuedeAtender) -> SistemaImplante:
    sistema = SistemaImplante(
        marca=datos.marca.strip(),
        linea=datos.linea.strip(),
        conexion=(datos.conexion or "").strip() or None,
        proveedor=(datos.proveedor or "").strip() or None,
    )
    db.add(sistema)
    db.commit()
    db.refresh(sistema)
    return sistema


# --- Implantes del paciente ----------------------------------------------------


@router.get("/pacientes/{paciente_id}/implantes", response_model=list[ImplanteLeer])
def implantes_del_paciente(paciente_id: int, db: BD, _: UsuarioAuth) -> list[Implante]:
    if db.get(Paciente, paciente_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El paciente no existe")
    return list(
        db.scalars(
            select(Implante)
            .where(Implante.paciente_id == paciente_id)
            .order_by(Implante.fecha_colocacion.desc().nulls_last(), Implante.id.desc())
        ).unique()
    )


@router.post(
    "/pacientes/{paciente_id}/implantes",
    response_model=ImplanteLeer,
    status_code=status.HTTP_201_CREATED,
)
def registrar_implante(paciente_id: int, datos: ImplanteCrear, db: BD, _: PuedeAtender) -> Implante:
    """Registra el implante colocado. Con `procedimiento_id`, hereda de la línea
    de consulta la pieza, el doctor y la fecha: sólo queda teclear el lote."""
    if db.get(Paciente, paciente_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El paciente no existe")
    _exigir_sistema(db, datos.sistema_implante_id)

    valores = datos.model_dump()
    linea: Procedimiento | None = None
    if datos.procedimiento_id is not None:
        linea = db.get(Procedimiento, datos.procedimiento_id)
        if linea is None or linea.paciente_id != paciente_id:
            raise HTTPException(NO_PROCESABLE, "procedimiento_id: la línea no es de este paciente")
        if not linea.servicio.es_implante:
            raise HTTPException(
                NO_PROCESABLE, f"«{linea.servicio.nombre}» no es un servicio de implante"
            )
        valores["codigo_fdi"] = valores["codigo_fdi"] or linea.codigo_fdi
        valores["doctor_id"] = valores["doctor_id"] or linea.doctor_id
        valores["fecha_colocacion"] = valores["fecha_colocacion"] or linea.fecha

    if valores["codigo_fdi"] is None:
        raise HTTPException(NO_PROCESABLE, "codigo_fdi: indica la pieza del implante")
    if db.get(Diente, valores["codigo_fdi"]) is None:
        raise HTTPException(NO_PROCESABLE, "codigo_fdi: la pieza no existe")
    if valores["doctor_id"] is None:
        raise HTTPException(NO_PROCESABLE, "doctor_id: indica quién lo colocó")
    _exigir_doctor(db, valores["doctor_id"])

    if datos.estado != EstadoImplante.PLANIFICADO:
        valores["fecha_colocacion"] = valores["fecha_colocacion"] or hoy()

    implante = Implante(paciente_id=paciente_id, **valores)
    if implante.estado != EstadoImplante.PLANIFICADO:
        implante.eventos.append(
            ImplanteEvento(
                fecha=implante.fecha_colocacion,
                tipo="colocacion",
                doctor_id=implante.doctor_id,
                isq=implante.isq,
                notas=f"Torque {implante.torque_ncm} Ncm" if implante.torque_ncm else None,
            )
        )
    db.add(implante)
    db.commit()
    db.refresh(implante)
    return implante


@router.patch("/implantes/{implante_id}", response_model=ImplanteLeer)
def actualizar_implante(
    implante_id: int, datos: ImplanteActualizar, db: BD, _: PuedeAtender
) -> Implante:
    implante = _implante(db, implante_id)
    cambios = datos.model_dump(exclude_unset=True)

    for obligatorio in ("lote", "estado", "sistema_implante_id"):
        if obligatorio in cambios and cambios[obligatorio] is None:
            raise HTTPException(NO_PROCESABLE, f"{obligatorio}: no puede quedar vacío")
    if "sistema_implante_id" in cambios:
        _exigir_sistema(db, cambios["sistema_implante_id"])

    for campo, valor in cambios.items():
        setattr(implante, campo, valor)
    db.commit()
    db.refresh(implante)
    return implante


@router.post(
    "/implantes/{implante_id}/eventos",
    response_model=ImplanteLeer,
    status_code=status.HTTP_201_CREATED,
)
def registrar_evento(implante_id: int, datos: EventoCrear, db: BD, _: PuedeAtender) -> Implante:
    implante = _implante(db, implante_id)
    _exigir_doctor(db, datos.doctor_id)

    fecha = datos.fecha or hoy()
    implante.eventos.append(
        ImplanteEvento(
            fecha=fecha,
            tipo=datos.tipo,
            doctor_id=datos.doctor_id or implante.doctor_id,
            isq=datos.isq,
            hallazgos=(datos.hallazgos or "").strip() or None,
            notas=(datos.notas or "").strip() or None,
        )
    )

    nuevo = datos.estado or _ESTADO_TRAS.get(datos.tipo)
    if nuevo is not None:
        implante.estado = nuevo
    if datos.tipo == "carga":
        implante.fecha_carga = fecha
    if datos.tipo == "colocacion" and implante.fecha_colocacion is None:
        implante.fecha_colocacion = fecha
    if datos.isq is not None:
        implante.isq = datos.isq

    db.commit()
    db.refresh(implante)
    return implante


# --- Trazabilidad --------------------------------------------------------------


@router.get("/implantes", response_model=list[ImplanteConPaciente])
def buscar_por_lote(
    db: BD,
    _: PuedeAtender,
    lote: Annotated[str, Query(min_length=2, description="Lote, completo o un tramo")],
) -> list[ImplanteConPaciente]:
    """A quién se le colocó un implante de ese lote: la respuesta a un retiro
    de producto del fabricante."""
    filas = db.execute(
        select(Implante, Paciente)
        .join(Paciente, Paciente.id == Implante.paciente_id)
        .where(coincide(Implante.lote, lote))
        .order_by(Implante.lote, Paciente.apellidos, Paciente.nombres)
    ).unique()
    return [
        ImplanteConPaciente(
            **ImplanteLeer.model_validate(implante).model_dump(),
            paciente_codigo=paciente.codigo,
            paciente_nombre=paciente.nombre_completo,
            paciente_telefono=paciente.celular or paciente.telefono,
        )
        for implante, paciente in filas
    ]
