"""Dependencias compartidas: sesión de base y usuario autenticado."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models.enums import RolUsuario
from app.models.organizacion import Usuario

BD = Annotated[Session, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)

NO_AUTORIZADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciales inválidas o sesión expirada",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_usuario_actual(
    db: BD,
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Usuario:
    if credenciales is None:
        raise NO_AUTORIZADO

    payload = decode_token(credenciales.credentials, "access")
    if payload is None:
        raise NO_AUTORIZADO

    usuario = db.get(Usuario, int(payload["sub"]))
    if usuario is None or not usuario.activo:
        raise NO_AUTORIZADO
    return usuario


UsuarioAuth = Annotated[Usuario, Depends(get_usuario_actual)]


def requiere_rol(*roles: RolUsuario) -> Callable[[Usuario], Usuario]:
    """Restringe un endpoint a ciertos roles.

    `admin` pasa siempre: es el rol de administración de la clínica y no tiene
    sentido excluirlo de una pantalla concreta.
    """
    permitidos = {RolUsuario.ADMIN, *roles}

    def verificar(usuario: UsuarioAuth) -> Usuario:
        if usuario.rol not in permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"El rol '{usuario.rol}' no tiene acceso a esta operación",
            )
        return usuario

    return verificar


def buscar_usuario_por_email(db: Session, email: str) -> Usuario | None:
    return db.scalar(select(Usuario).where(Usuario.email == email.lower().strip()))
