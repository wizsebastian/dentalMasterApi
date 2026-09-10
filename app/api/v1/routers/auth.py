"""Inicio de sesión y renovación de tokens."""

from fastapi import APIRouter, HTTPException, status

from app.core.deps import BD, UsuarioAuth, buscar_usuario_por_email
from app.core.security import create_token, decode_token, verify_password
from app.models.organizacion import Usuario
from app.schemas.auth import Credenciales, Refresco, Tokens, UsuarioActual

router = APIRouter(prefix="/auth", tags=["auth"])


def _emitir(usuario_id: int, rol: str) -> Tokens:
    return Tokens(
        access_token=create_token(str(usuario_id), "access", rol=rol),
        refresh_token=create_token(str(usuario_id), "refresh"),
    )


@router.post("/login", response_model=Tokens)
def login(datos: Credenciales, db: BD) -> Tokens:
    usuario = buscar_usuario_por_email(db, datos.email)

    # Mismo mensaje para email inexistente y contraseña incorrecta: distinguirlos
    # permitiría enumerar qué cuentas existen.
    if usuario is None or not verify_password(datos.password, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
        )
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta está desactivada",
        )

    return _emitir(usuario.id, usuario.rol)


@router.post("/refresh", response_model=Tokens)
def refrescar(datos: Refresco, db: BD) -> Tokens:
    payload = decode_token(datos.refresh_token, "refresh")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El token de refresco no es válido o expiró",
        )

    usuario = db.get(Usuario, int(payload["sub"]))
    if usuario is None or not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El token de refresco no es válido o expiró",
        )

    return _emitir(usuario.id, usuario.rol)


@router.get("/me", response_model=UsuarioActual)
def yo(usuario: UsuarioAuth) -> UsuarioActual:
    return UsuarioActual(
        id=usuario.id,
        email=usuario.email,
        rol=usuario.rol,
        doctor_id=usuario.doctor_id,
        doctor_nombre=usuario.doctor.nombre_completo if usuario.doctor else None,
    )
