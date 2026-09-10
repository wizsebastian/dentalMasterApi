from pydantic import BaseModel, EmailStr

from app.models.enums import RolUsuario


class Credenciales(BaseModel):
    email: EmailStr
    password: str


class Tokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class Refresco(BaseModel):
    refresh_token: str


class UsuarioActual(BaseModel):
    """Identidad del usuario en sesión, para la cabecera de la aplicación."""

    id: int
    email: str
    rol: RolUsuario
    doctor_id: int | None = None
    doctor_nombre: str | None = None
