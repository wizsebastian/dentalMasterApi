"""Pacientes: alta, búsqueda, edición y alertas clínicas."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.core.deps import BD, UsuarioAuth, requiere_rol
from app.models.enums import RolUsuario
from app.models.organizacion import Usuario
from app.models.paciente import Paciente
from app.schemas.comun import Pagina
from app.schemas.paciente import (
    Alerta,
    PacienteActualizar,
    PacienteCrear,
    PacienteDetalle,
    PacienteResumen,
)

router = APIRouter(prefix="/pacientes", tags=["pacientes"])

# Quien atiende o agenda puede dar de alta y editar pacientes; facturación no.
PuedeEditar = Annotated[
    Usuario,
    Depends(requiere_rol(RolUsuario.DOCTOR, RolUsuario.ASISTENTE, RolUsuario.RECEPCION)),
]


def siguiente_codigo(db: Session) -> str:
    """Genera el número de expediente: PAC-2026-0001.

    El correlativo se calcula sobre los expedientes del año en curso, así que
    reinicia cada enero.
    """
    anio = datetime.now(UTC).year
    prefijo = f"PAC-{anio}-"
    ultimo = db.scalar(select(func.max(Paciente.codigo)).where(Paciente.codigo.like(f"{prefijo}%")))
    consecutivo = int(ultimo.removeprefix(prefijo)) + 1 if ultimo else 1
    return f"{prefijo}{consecutivo:04d}"


def _filtrar(consulta: Select, buscar: str | None, incluir_inactivos: bool) -> Select:
    if not incluir_inactivos:
        consulta = consulta.where(Paciente.activo)

    if buscar:
        patron = f"%{buscar.strip()}%"
        consulta = consulta.where(
            or_(
                Paciente.nombres.ilike(patron),
                Paciente.apellidos.ilike(patron),
                Paciente.codigo.ilike(patron),
                Paciente.documento.ilike(patron),
                # Permite buscar "Juan Peña" aunque nombres y apellidos sean
                # columnas distintas.
                (Paciente.nombres + " " + Paciente.apellidos).ilike(patron),
            )
        )
    return consulta


@router.get("", response_model=Pagina[PacienteResumen])
def listar(
    db: BD,
    _: UsuarioAuth,
    buscar: str | None = Query(default=None, description="Nombre, expediente o documento"),
    incluir_inactivos: bool = False,
    limite: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Pagina[PacienteResumen]:
    total = db.scalar(
        _filtrar(select(func.count()).select_from(Paciente), buscar, incluir_inactivos)
    )
    filas = db.scalars(
        _filtrar(select(Paciente), buscar, incluir_inactivos)
        .order_by(Paciente.apellidos, Paciente.nombres)
        .limit(limite)
        .offset(offset)
    ).all()

    return Pagina(
        items=[PacienteResumen.model_validate(p) for p in filas],
        total=total or 0,
        limite=limite,
        offset=offset,
    )


def _obtener(db: Session, paciente_id: int) -> Paciente:
    paciente = db.scalar(
        select(Paciente).where(Paciente.id == paciente_id).options(selectinload(Paciente.contactos))
    )
    if paciente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El paciente no existe")
    return paciente


@router.get("/{paciente_id}", response_model=PacienteDetalle)
def obtener(paciente_id: int, db: BD, _: UsuarioAuth) -> Paciente:
    return _obtener(db, paciente_id)


@router.post("", response_model=PacienteDetalle, status_code=status.HTTP_201_CREATED)
def crear(datos: PacienteCrear, db: BD, _: PuedeEditar) -> Paciente:
    if datos.documento and db.scalar(select(Paciente).where(Paciente.documento == datos.documento)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Ya existe un paciente con el documento {datos.documento}",
        )

    ahora = datetime.now(UTC)
    paciente = Paciente(
        **datos.model_dump(exclude_none=False),
        codigo=siguiente_codigo(db),
        activo=True,
        creado_en=ahora,
        actualizado_en=ahora,
    )
    db.add(paciente)
    db.commit()
    db.refresh(paciente)
    return paciente


@router.patch("/{paciente_id}", response_model=PacienteDetalle)
def actualizar(paciente_id: int, datos: PacienteActualizar, db: BD, _: PuedeEditar) -> Paciente:
    paciente = _obtener(db, paciente_id)

    cambios = datos.model_dump(exclude_unset=True)
    if "documento" in cambios and cambios["documento"]:
        duplicado = db.scalar(
            select(Paciente).where(
                Paciente.documento == cambios["documento"], Paciente.id != paciente_id
            )
        )
        if duplicado:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Ya existe un paciente con el documento {cambios['documento']}",
            )

    for campo, valor in cambios.items():
        setattr(paciente, campo, valor)
    paciente.actualizado_en = datetime.now(UTC)

    db.commit()
    db.refresh(paciente)
    return paciente


@router.get("/{paciente_id}/alertas", response_model=list[Alerta])
def alertas(paciente_id: int, db: BD, _: UsuarioAuth) -> list[Alerta]:
    """Condiciones de riesgo alto y alergias, para la cabecera clínica.

    Sale de la vista `v_alertas_paciente`, que ya cruza ambas fuentes.
    """
    _obtener(db, paciente_id)

    filas = db.execute(
        text(
            "SELECT tipo, detalle, riesgo FROM v_alertas_paciente "
            "WHERE paciente_id = :pid ORDER BY tipo, detalle"
        ),
        {"pid": paciente_id},
    ).mappings()

    return [Alerta.model_validate(dict(f)) for f in filas]
