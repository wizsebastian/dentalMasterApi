"""Cuentas de acceso. Sólo administración.

Las contraseñas pasan por la misma política que `python -m app.cli crear-usuario`
(`revisar_password`): la pantalla no es una vía para saltársela.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import BD, requiere_rol
from app.core.security import MAX_PASSWORD_BYTES, hash_password, revisar_password
from app.models.enums import RolUsuario
from app.models.organizacion import Doctor, Usuario
from app.schemas.catalogo import PasswordNueva, UsuarioActualizar, UsuarioCrear, UsuarioLeer

router = APIRouter(prefix="/usuarios", tags=["usuarios"])

SoloAdmin = Annotated[Usuario, Depends(requiere_rol())]


def _leer(usuario: Usuario) -> UsuarioLeer:
    return UsuarioLeer(
        id=usuario.id,
        email=usuario.email,
        rol=usuario.rol,
        doctor_id=usuario.doctor_id,
        doctor_nombre=usuario.doctor.nombre_completo if usuario.doctor else None,
        activo=usuario.activo,
        creado_en=usuario.creado_en,
    )


def _obtener(db: Session, usuario_id: int) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El usuario no existe")
    return usuario


def _hash_validado(password: str) -> str:
    motivo = revisar_password(password)
    if motivo is None and len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        motivo = f"excede {MAX_PASSWORD_BYTES} bytes"
    if motivo:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"password: {motivo}")
    return hash_password(password)


def _exigir_doctor(db: Session, doctor_id: int | None) -> None:
    if doctor_id is not None and db.get(Doctor, doctor_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "doctor_id: el doctor no existe")


@router.get("", response_model=list[UsuarioLeer])
def listar(db: BD, _: SoloAdmin) -> list[UsuarioLeer]:
    return [_leer(u) for u in db.scalars(select(Usuario).order_by(Usuario.email))]


@router.post("", response_model=UsuarioLeer, status_code=status.HTTP_201_CREATED)
def crear(datos: UsuarioCrear, db: BD, _: SoloAdmin) -> UsuarioLeer:
    email = datos.email.lower().strip()
    if db.scalar(select(Usuario.id).where(Usuario.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe un usuario con el email {email}")
    _exigir_doctor(db, datos.doctor_id)

    usuario = Usuario(
        email=email,
        password_hash=_hash_validado(datos.password),
        rol=datos.rol,
        doctor_id=datos.doctor_id,
        activo=True,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return _leer(usuario)


@router.patch("/{usuario_id}", response_model=UsuarioLeer)
def actualizar(usuario_id: int, datos: UsuarioActualizar, db: BD, actual: SoloAdmin) -> UsuarioLeer:
    usuario = _obtener(db, usuario_id)
    cambios = datos.model_dump(exclude_unset=True)

    # Un administrador no puede dejarse a sí mismo fuera: si es el único, nadie
    # podría deshacerlo desde la pantalla.
    if usuario.id == actual.id and (
        cambios.get("activo") is False or cambios.get("rol") not in (None, RolUsuario.ADMIN)
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No puedes desactivar tu propia cuenta ni quitarte el rol de administración",
        )

    if "doctor_id" in cambios:
        _exigir_doctor(db, cambios["doctor_id"])
        usuario.doctor_id = cambios["doctor_id"]
    if cambios.get("rol") is not None:
        usuario.rol = cambios["rol"]
    if cambios.get("activo") is not None:
        usuario.activo = cambios["activo"]

    db.commit()
    db.refresh(usuario)
    return _leer(usuario)


@router.post("/{usuario_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def cambiar_password(usuario_id: int, datos: PasswordNueva, db: BD, _: SoloAdmin) -> None:
    usuario = _obtener(db, usuario_id)
    usuario.password_hash = _hash_validado(datos.password)
    db.commit()
