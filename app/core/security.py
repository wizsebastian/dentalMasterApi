"""Hashing de contraseñas y emisión/validación de JWT.

Se usan `bcrypt` y `PyJWT` directamente. Ni passlib ni python-jose: ambos están
sin mantenimiento y python-jose además aborta con SIGILL en aarch64.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
import jwt
from jwt import InvalidTokenError

from app.core.config import settings

TokenType = Literal["access", "refresh"]

# bcrypt trunca silenciosamente en 72 bytes; se rechaza antes para que una
# contraseña larga no acabe validando con sólo su prefijo.
MAX_PASSWORD_BYTES = 72


def hash_password(plain: str) -> str:
    encoded = plain.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(f"La contraseña excede {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verifica la contraseña. Un hash con formato inválido cuenta como fallo.

    `03_seed_demo.sql` inserta el marcador '$2b$12$CAMBIAR_ESTE_HASH_EN_PRODUCCION',
    que no es un hash bcrypt válido y haría lanzar a checkpw.
    """
    encoded = plain.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, hashed.encode("utf-8"))
    except ValueError:
        return False


def create_token(subject: str, token_type: TokenType, **claims: Any) -> str:
    ttl = (
        timedelta(minutes=settings.access_token_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_days)
    )
    ahora = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "exp": ahora + ttl,
        "iat": ahora,
        **claims,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any] | None:
    """Devuelve el payload, o None si el token es inválido, expiró o es de otro tipo."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except InvalidTokenError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload
