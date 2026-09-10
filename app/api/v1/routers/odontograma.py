"""Odontograma: versión vigente, historial y registro de hallazgos."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import BD, UsuarioAuth, requiere_rol
from app.models.enums import RolUsuario
from app.models.odontograma import Odontograma, OdontogramaDiente, OdontogramaHallazgo
from app.models.organizacion import Usuario
from app.models.paciente import Paciente
from app.schemas.odontograma import (
    DienteEstado,
    HallazgoActualizar,
    HallazgoCrear,
    HallazgoLeer,
    OdontogramaCrear,
    OdontogramaLeer,
    OdontogramaResumen,
)
from app.services import odontograma as servicio

router = APIRouter(tags=["odontograma"])

# El odontograma es un registro clínico: lo firma quien atiende.
PuedeRegistrar = Annotated[Usuario, Depends(requiere_rol(RolUsuario.DOCTOR, RolUsuario.ASISTENTE))]


def _cargar_completo(db: BD, odontograma_id: int) -> Odontograma:
    odontograma = db.scalar(
        select(Odontograma)
        .where(Odontograma.id == odontograma_id)
        .options(
            selectinload(Odontograma.hallazgos).selectinload(OdontogramaHallazgo.condicion),
            selectinload(Odontograma.dientes),
        )
    )
    if odontograma is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El odontograma no existe")
    return odontograma


def _exigir_paciente(db: BD, paciente_id: int) -> None:
    if not db.get(Paciente, paciente_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El paciente no existe")


@router.get("/pacientes/{paciente_id}/odontograma", response_model=OdontogramaLeer)
def vigente(paciente_id: int, db: BD, _: UsuarioAuth) -> Odontograma:
    """Versión vigente del odontograma, lista para dibujar."""
    _exigir_paciente(db, paciente_id)

    actual = servicio.obtener_vigente(db, paciente_id)
    if actual is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "El paciente aún no tiene odontograma. Crea la primera versión.",
        )
    return _cargar_completo(db, actual.id)


@router.get(
    "/pacientes/{paciente_id}/odontograma/versiones",
    response_model=list[OdontogramaResumen],
)
def versiones(paciente_id: int, db: BD, _: UsuarioAuth) -> list[Odontograma]:
    """Historial completo, de la más reciente a la más antigua."""
    _exigir_paciente(db, paciente_id)
    return list(
        db.scalars(
            select(Odontograma)
            .where(Odontograma.paciente_id == paciente_id)
            .order_by(Odontograma.version.desc())
        ).all()
    )


@router.get("/odontogramas/{odontograma_id}", response_model=OdontogramaLeer)
def por_id(odontograma_id: int, db: BD, _: UsuarioAuth) -> Odontograma:
    """Una versión concreta, incluidas las históricas (solo lectura)."""
    return _cargar_completo(db, odontograma_id)


@router.post(
    "/pacientes/{paciente_id}/odontograma",
    response_model=OdontogramaLeer,
    status_code=status.HTTP_201_CREATED,
)
def nueva_version(
    paciente_id: int, datos: OdontogramaCrear, db: BD, usuario: PuedeRegistrar
) -> Odontograma:
    """Cierra la versión vigente y abre la siguiente.

    La anterior queda como historial de solo lectura: no se borra nunca.
    """
    _exigir_paciente(db, paciente_id)

    nueva = servicio.crear_version(
        db,
        paciente_id,
        denticion=datos.denticion,
        doctor_id=usuario.doctor_id,
        observaciones=datos.observaciones,
        copiar_hallazgos=datos.copiar_hallazgos,
    )
    db.commit()
    return _cargar_completo(db, nueva.id)


@router.post(
    "/odontogramas/{odontograma_id}/hallazgos",
    response_model=HallazgoLeer,
    status_code=status.HTTP_201_CREATED,
)
def registrar_hallazgo(
    odontograma_id: int, datos: HallazgoCrear, db: BD, usuario: PuedeRegistrar
) -> OdontogramaHallazgo:
    odontograma = servicio.exigir_vigente(db, odontograma_id)
    servicio.validar_hallazgo(
        db,
        odontograma,
        codigo_fdi=datos.codigo_fdi,
        superficie=datos.superficie,
        condicion_dental_id=datos.condicion_dental_id,
    )

    # El esquema tiene UNIQUE(odontograma, pieza, cara, condición, estado): un
    # mismo hallazgo repetido se responde como conflicto, no como error 500.
    duplicado = db.scalar(
        select(OdontogramaHallazgo).where(
            OdontogramaHallazgo.odontograma_id == odontograma_id,
            OdontogramaHallazgo.codigo_fdi == datos.codigo_fdi,
            OdontogramaHallazgo.superficie.is_not_distinct_from(datos.superficie),
            OdontogramaHallazgo.condicion_dental_id == datos.condicion_dental_id,
            OdontogramaHallazgo.estado == datos.estado,
        )
    )
    if duplicado is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Ese hallazgo ya está registrado en la pieza {datos.codigo_fdi}",
        )

    hallazgo = OdontogramaHallazgo(
        odontograma_id=odontograma_id,
        codigo_fdi=datos.codigo_fdi,
        superficie=datos.superficie,
        condicion_dental_id=datos.condicion_dental_id,
        estado=datos.estado,
        doctor_id=usuario.doctor_id,
        fecha=date.today(),
        notas=datos.notas,
    )
    db.add(hallazgo)
    db.commit()
    db.refresh(hallazgo)
    return hallazgo


@router.patch("/odontogramas/{odontograma_id}/hallazgos/{hallazgo_id}", response_model=HallazgoLeer)
def actualizar_hallazgo(
    odontograma_id: int,
    hallazgo_id: int,
    datos: HallazgoActualizar,
    db: BD,
    _: PuedeRegistrar,
) -> OdontogramaHallazgo:
    servicio.exigir_vigente(db, odontograma_id)

    hallazgo = db.get(OdontogramaHallazgo, hallazgo_id)
    if hallazgo is None or hallazgo.odontograma_id != odontograma_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El hallazgo no existe")

    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(hallazgo, campo, valor)

    db.commit()
    db.refresh(hallazgo)
    return hallazgo


@router.delete(
    "/odontogramas/{odontograma_id}/hallazgos/{hallazgo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def borrar_hallazgo(odontograma_id: int, hallazgo_id: int, db: BD, _: PuedeRegistrar) -> None:
    """Elimina un hallazgo mal registrado en la versión vigente.

    No es un borrado clínico: las versiones históricas son intocables, así que
    esto sólo corrige lo que se acaba de anotar por error.
    """
    servicio.exigir_vigente(db, odontograma_id)

    hallazgo = db.get(OdontogramaHallazgo, hallazgo_id)
    if hallazgo is None or hallazgo.odontograma_id != odontograma_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El hallazgo no existe")

    db.delete(hallazgo)
    db.commit()


@router.put("/odontogramas/{odontograma_id}/dientes/{codigo_fdi}", response_model=DienteEstado)
def estado_pieza(
    odontograma_id: int,
    codigo_fdi: int,
    datos: DienteEstado,
    db: BD,
    _: PuedeRegistrar,
) -> OdontogramaDiente:
    """Registra movilidad, sondaje, recesión y sangrado de una pieza."""
    if datos.codigo_fdi != codigo_fdi:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "El código FDI de la ruta y el del cuerpo no coinciden",
        )

    odontograma = servicio.exigir_vigente(db, odontograma_id)
    servicio.validar_pieza(db, odontograma, codigo_fdi)

    fila = db.scalar(
        select(OdontogramaDiente).where(
            OdontogramaDiente.odontograma_id == odontograma_id,
            OdontogramaDiente.codigo_fdi == codigo_fdi,
        )
    )
    if fila is None:
        fila = OdontogramaDiente(odontograma_id=odontograma_id, codigo_fdi=codigo_fdi)
        db.add(fila)

    for campo, valor in datos.model_dump(exclude={"codigo_fdi"}).items():
        setattr(fila, campo, valor)

    db.commit()
    db.refresh(fila)
    return fila
