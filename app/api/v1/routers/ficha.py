"""Ficha médica del paciente."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import BD, UsuarioAuth, requiere_rol
from app.models.enums import RolUsuario
from app.models.organizacion import Usuario
from app.models.paciente import (
    FichaAlergia,
    FichaCondicion,
    FichaMedica,
    FichaMedicamento,
    Paciente,
)
from app.schemas.ficha import FichaGuardar, FichaLeer

router = APIRouter(prefix="/pacientes/{paciente_id}/ficha", tags=["ficha médica"])

# La historia clínica la escribe quien atiende, no recepción ni facturación.
PuedeEditarFicha = Annotated[
    Usuario, Depends(requiere_rol(RolUsuario.DOCTOR, RolUsuario.ASISTENTE))
]


def _cargar(db: Session, paciente_id: int) -> FichaMedica:
    if not db.get(Paciente, paciente_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El paciente no existe")

    ficha = db.scalar(
        select(FichaMedica)
        .where(FichaMedica.paciente_id == paciente_id)
        .options(
            selectinload(FichaMedica.condiciones),
            selectinload(FichaMedica.alergias),
            selectinload(FichaMedica.medicamentos),
        )
    )
    if ficha is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "El paciente aún no tiene ficha médica. Guárdala para crearla.",
        )
    return ficha


@router.get("", response_model=FichaLeer)
def obtener(paciente_id: int, db: BD, _: UsuarioAuth) -> FichaMedica:
    return _cargar(db, paciente_id)


@router.put("", response_model=FichaLeer)
def guardar(
    paciente_id: int, datos: FichaGuardar, db: BD, usuario: PuedeEditarFicha
) -> FichaMedica:
    """Crea o reemplaza la ficha completa.

    Es un PUT y no un PATCH a propósito: la ficha es un formulario que el doctor
    revisa entero en cada visita. Las tres colecciones se reemplazan, así que
    quitar una alergia es simplemente no enviarla.
    """
    if not db.get(Paciente, paciente_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El paciente no existe")

    ahora = datetime.now(UTC)
    ficha = db.scalar(select(FichaMedica).where(FichaMedica.paciente_id == paciente_id))

    if ficha is None:
        ficha = FichaMedica(paciente_id=paciente_id, creado_en=ahora, actualizado_en=ahora)
        db.add(ficha)

    for campo, valor in datos.model_dump(
        exclude={"condiciones", "alergias", "medicamentos"}
    ).items():
        setattr(ficha, campo, valor)

    ficha.actualizado_por = usuario.doctor_id
    ficha.actualizado_en = ahora
    db.flush()

    # Las colecciones se reemplazan enteras: se vacían y se reconstruyen dentro
    # de la misma transacción.
    ficha.condiciones.clear()
    ficha.alergias.clear()
    ficha.medicamentos.clear()
    db.flush()

    vistos_condicion: set[int] = set()
    for condicion in datos.condiciones:
        if condicion.condicion_medica_id in vistos_condicion:
            continue  # el PK compuesto no admite duplicados
        vistos_condicion.add(condicion.condicion_medica_id)
        ficha.condiciones.append(FichaCondicion(**condicion.model_dump()))

    vistas_alergia: set[int] = set()
    for alergia in datos.alergias:
        if alergia.alergia_id in vistas_alergia:
            continue
        vistas_alergia.add(alergia.alergia_id)
        ficha.alergias.append(FichaAlergia(**alergia.model_dump()))

    for medicamento in datos.medicamentos:
        ficha.medicamentos.append(FichaMedicamento(**medicamento.model_dump()))

    db.commit()
    return _cargar(db, paciente_id)
