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

TokenType = Literal["access", "refresh", "firma"]

# bcrypt trunca silenciosamente en 72 bytes; se rechaza antes para que una
# contraseña larga no acabe validando con sólo su prefijo.
MAX_PASSWORD_BYTES = 72

MINUTOS_ENLACE_FIRMA = 120


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


MIN_PASSWORD = 12


def revisar_password(password: str) -> str | None:
    """Devuelve el motivo de rechazo, o None si la contraseña es aceptable.

    La longitud sola no basta: '12345678912345' tiene catorce caracteres y se
    adivina al primer intento. Se rechazan secuencias, repeticiones y patrones
    de teclado, que es justo lo que se escribe cuando el único requisito es un
    mínimo de longitud.
    """
    if len(password) < MIN_PASSWORD:
        return f"debe tener al menos {MIN_PASSWORD} caracteres"

    if len(set(password)) < 5:
        return "usa muy pocos caracteres distintos"

    minuscula = password.lower()

    for base in ("0123456789", "abcdefghijklmnopqrstuvwxyz"):
        for referencia in (base, base[::-1]):
            for inicio in range(len(referencia) - 5):
                if referencia[inicio : inicio + 6] in minuscula:
                    return "contiene una secuencia previsible (12345…, abcde…)"

    for patron in ("qwerty", "asdfgh", "password", "contrasena", "dental", "admin"):
        if patron in minuscula:
            return f"contiene un patrón previsible ({patron})"

    if password.isdigit():
        return "no puede ser sólo dígitos"

    return None


def create_token(subject: str, token_type: TokenType, **claims: Any) -> str:
    if token_type == "access":
        ttl = timedelta(minutes=settings.access_token_minutes)
    elif token_type == "refresh":
        ttl = timedelta(days=settings.refresh_token_days)
    else:
        # El enlace para firmar un documento: sirve sólo para ese documento y caduca pronto.
        ttl = timedelta(hours=MINUTOS_ENLACE_FIRMA / 60)
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
