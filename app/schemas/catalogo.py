"""Schemas del catálogo de servicios y de la configuración de la clínica."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.telefono import Telefono
from app.models.enums import EstadoCita, RolUsuario

ORM = ConfigDict(from_attributes=True)
ESTRICTO = ConfigDict(extra="forbid")

Dinero = Decimal


# --- Catálogos de sólo lectura -------------------------------------------------


class CondicionMedicaCatalogo(BaseModel):
    model_config = ORM

    id: int
    codigo: str
    nombre: str
    riesgo: str | None
    alerta: str | None


class AlergiaCatalogo(BaseModel):
    model_config = ORM

    id: int
    codigo: str
    nombre: str
    tipo: str | None


class EstadoCitaLeer(BaseModel):
    """Un estado de la agenda, con el color de su insignia.

    El color viaja desde aquí para que ninguna pantalla lo escriba a mano, igual
    que los de `condicion_dental`.
    """

    valor: EstadoCita
    etiqueta: str
    color_hex: str
    ocupa_agenda: bool = Field(
        default=True, description="Falso en los estados que liberan el hueco"
    )


# --- Categorías y listas de precio --------------------------------------------


class CategoriaLeer(BaseModel):
    model_config = ORM

    id: int
    codigo: str
    nombre: str
    orden: int | None
    servicios: int = Field(default=0, description="Servicios que cuelgan de la categoría")


class CategoriaCrear(BaseModel):
    model_config = ESTRICTO

    nombre: str = Field(min_length=1, max_length=80)
    codigo: str | None = Field(default=None, min_length=2, max_length=8, pattern=r"^[A-Z0-9]+$")
    orden: int | None = None


class CategoriaActualizar(BaseModel):
    model_config = ESTRICTO

    nombre: str | None = Field(default=None, min_length=1, max_length=80)
    orden: int | None = None


class ListaPrecioLeer(BaseModel):
    model_config = ORM

    id: int
    codigo: str
    nombre: str
    moneda: str
    aseguradora_id: int | None
    activo: bool


class ListaPrecioCrear(BaseModel):
    """Una tarifa nueva nace copiando los precios de otra, con un ajuste."""

    model_config = ESTRICTO

    nombre: str = Field(min_length=1, max_length=80)
    aseguradora_id: int | None = Field(default=None, description="Vacío: otra tarifa particular")
    copiar_de: int | None = Field(default=None, description="Por defecto, la particular")
    ajuste_pct: Decimal = Field(
        default=Decimal(0), ge=-90, le=300, description="−10 la deja un 10 % por debajo"
    )
    cobertura_pct: Decimal = Field(
        default=Decimal(0), ge=0, le=100, description="Lo que cubre el seguro, por defecto"
    )


class ListaPrecioActualizar(BaseModel):
    model_config = ESTRICTO

    nombre: str | None = Field(default=None, min_length=1, max_length=80)
    activo: bool | None = None


class AseguradoraLeer(BaseModel):
    model_config = ORM

    id: int
    codigo: str
    nombre: str
    telefono: str | None


# --- Servicios -----------------------------------------------------------------


class PrecioLeer(BaseModel):
    model_config = ORM

    lista_precio_id: int
    precio: Dinero
    costo: Dinero | None
    cobertura_pct: Decimal | None = None


class PrecioEscribir(BaseModel):
    model_config = ESTRICTO

    lista_precio_id: int
    precio: Dinero = Field(ge=0, max_digits=12, decimal_places=2)
    costo: Dinero | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    cobertura_pct: Decimal | None = Field(
        default=None, ge=0, le=100, description="Porcentaje que cubre el seguro en esta tarifa"
    )


class ServicioBase(BaseModel):
    categoria_id: int
    nombre: str = Field(min_length=1, max_length=160)
    descripcion: str | None = None
    requiere_diente: bool = False
    requiere_superficie: bool = False
    es_implante: bool = False
    duracion_min: int = Field(default=30, ge=5, le=480)
    sesiones: int = Field(default=1, ge=1, le=50)
    condicion_resultante_id: int | None = None


class ServicioCrear(ServicioBase):
    """El `codigo` lo genera el servidor a partir de la categoría."""

    model_config = ESTRICTO

    precios: list[PrecioEscribir] = Field(min_length=1)


class ServicioActualizar(BaseModel):
    """PATCH. `precios` reemplaza el precio de las listas que nombre; las que no
    nombre se quedan como están."""

    model_config = ESTRICTO

    categoria_id: int | None = None
    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    descripcion: str | None = None
    requiere_diente: bool | None = None
    requiere_superficie: bool | None = None
    es_implante: bool | None = None
    duracion_min: int | None = Field(default=None, ge=5, le=480)
    sesiones: int | None = Field(default=None, ge=1, le=50)
    condicion_resultante_id: int | None = None
    activo: bool | None = None
    precios: list[PrecioEscribir] | None = None


class ServicioLeer(ServicioBase):
    model_config = ORM

    id: int
    codigo: str
    categoria_nombre: str
    activo: bool
    precios: list[PrecioLeer] = []
    en_uso: bool = Field(default=False, description="Aparece en citas, planes o procedimientos")


# --- Especialidades ------------------------------------------------------------


class EspecialidadLeer(BaseModel):
    model_config = ORM

    id: int
    codigo: str
    nombre: str
    descripcion: str | None
    activo: bool
    planes: int = Field(default=0, description="Planes de tratamiento abiertos con ella")
    doctores: int = Field(default=0, description="Doctores que la ejercen")


class EspecialidadCrear(BaseModel):
    model_config = ESTRICTO

    nombre: str = Field(min_length=1, max_length=80)
    descripcion: str | None = None
    codigo: str | None = Field(default=None, min_length=2, max_length=8, pattern=r"^[A-Z0-9]+$")


class EspecialidadActualizar(BaseModel):
    model_config = ESTRICTO

    nombre: str | None = Field(default=None, min_length=1, max_length=80)
    descripcion: str | None = None
    activo: bool | None = None


# --- Unidades dentales ---------------------------------------------------------


class UnidadLeer(BaseModel):
    model_config = ORM

    id: int
    sede_id: int
    nombre: str
    alquilada: bool
    orden: int
    activo: bool


class UnidadCrear(BaseModel):
    model_config = ESTRICTO

    nombre: str = Field(min_length=1, max_length=60)
    alquilada: bool = False
    orden: int = 0
    sede_id: int | None = Field(default=None, description="Por defecto, la sede principal")


class UnidadActualizar(BaseModel):
    model_config = ESTRICTO

    nombre: str | None = Field(default=None, min_length=1, max_length=60)
    alquilada: bool | None = None
    orden: int | None = None
    activo: bool | None = None


# --- La clínica ----------------------------------------------------------------


class ClinicaActualizar(BaseModel):
    """PATCH de los datos que salen en cada impreso y en los mensajes."""

    model_config = ESTRICTO

    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    rnc: str | None = Field(default=None, max_length=30)
    direccion: str | None = Field(default=None, max_length=200)
    ciudad: str | None = Field(default=None, max_length=80)
    telefono: Telefono = None
    whatsapp: Telefono = None
    email: EmailStr | None = None
    web: str | None = Field(default=None, max_length=120)


# --- Doctores ------------------------------------------------------------------


class DoctorEspecialidadLeer(BaseModel):
    model_config = ORM

    especialidad_id: int
    nombre: str
    principal: bool


class DoctorLeer(BaseModel):
    model_config = ORM

    id: int
    documento: str
    nombres: str
    apellidos: str
    nombre_completo: str
    licencia: str | None
    email: str | None
    telefono: str | None
    porcentaje_comision: Decimal | None
    activo: bool
    especialidades: list[DoctorEspecialidadLeer] = []


class DoctorCrear(BaseModel):
    """El tratamiento (Dr./Dra.) no forma parte del nombre: la interfaz lo antepone."""

    model_config = ESTRICTO

    documento: str = Field(min_length=5, max_length=20)
    nombres: str = Field(min_length=1, max_length=120)
    apellidos: str = Field(min_length=1, max_length=120)
    licencia: str | None = None
    email: EmailStr | None = None
    telefono: Telefono = None
    porcentaje_comision: Decimal = Field(default=Decimal(0), ge=0, le=100)
    especialidad_ids: list[int] = Field(
        default=[], description="La primera es la especialidad principal"
    )


class DoctorActualizar(BaseModel):
    model_config = ESTRICTO

    documento: str | None = Field(default=None, min_length=5, max_length=20)
    nombres: str | None = Field(default=None, min_length=1, max_length=120)
    apellidos: str | None = Field(default=None, min_length=1, max_length=120)
    licencia: str | None = None
    email: EmailStr | None = None
    telefono: Telefono = None
    porcentaje_comision: Decimal | None = Field(default=None, ge=0, le=100)
    activo: bool | None = None
    especialidad_ids: list[int] | None = None


# --- Usuarios ------------------------------------------------------------------


class UsuarioLeer(BaseModel):
    id: int
    email: str
    rol: RolUsuario
    doctor_id: int | None
    doctor_nombre: str | None
    activo: bool
    creado_en: datetime


class UsuarioCrear(BaseModel):
    model_config = ESTRICTO

    email: EmailStr
    rol: RolUsuario
    doctor_id: int | None = None
    password: str


class UsuarioActualizar(BaseModel):
    model_config = ESTRICTO

    rol: RolUsuario | None = None
    doctor_id: int | None = None
    activo: bool | None = None


class PasswordNueva(BaseModel):
    model_config = ESTRICTO

    password: str
