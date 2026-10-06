"""Configuración de la clínica: especialidades, unidades dentales y doctores.

Lectura para cualquiera con sesión (alimentan los selectores de la agenda y de
los planes); escritura sólo para administración.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import BD, UsuarioAuth, requiere_rol
from app.models.archivo import Archivo
from app.models.clinico import Cita, Consulta
from app.models.organizacion import (
    Doctor,
    DoctorEspecialidad,
    Especialidad,
    Sede,
    UnidadDental,
    Usuario,
)
from app.models.plan import PlanTratamiento
from app.schemas.agenda import ClinicaLeer
from app.schemas.catalogo import (
    ClinicaActualizar,
    DoctorActualizar,
    DoctorCrear,
    DoctorEspecialidadLeer,
    DoctorLeer,
    EspecialidadActualizar,
    EspecialidadCrear,
    EspecialidadLeer,
    UnidadActualizar,
    UnidadCrear,
    UnidadLeer,
)
from app.services import almacen
from app.services.catalogo import codigo_desde_nombre

router = APIRouter(tags=["configuración de la clínica"])

SoloAdmin = Annotated[Usuario, Depends(requiere_rol())]


# --- La clínica: lo que sale en cada impreso -------------------------------------


def _sede(db: Session) -> Sede:
    sede = db.scalar(select(Sede).where(Sede.activo).order_by(Sede.id))
    if sede is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No hay ninguna sede registrada")
    return sede


@router.patch("/catalogos/clinica", response_model=ClinicaLeer)
def actualizar_clinica(datos: ClinicaActualizar, db: BD, _: SoloAdmin) -> Sede:
    """Nombre, RNC, dirección y contacto de la clínica. Todo el sistema los usa:
    membrete de impresos, recordatorios y variables de las plantillas."""
    sede = _sede(db)
    cambios = datos.model_dump(exclude_unset=True)
    if "nombre" in cambios and cambios["nombre"] is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "nombre: no puede quedar vacío")
    for campo, valor in cambios.items():
        setattr(sede, campo, valor.strip() if isinstance(valor, str) else valor)
    db.commit()
    db.refresh(sede)
    return sede


@router.put("/catalogos/clinica/logo", response_model=ClinicaLeer)
def subir_logo(db: BD, usuario: SoloAdmin, archivo: Annotated[UploadFile, File()]) -> Sede:
    """El logo que llevan los impresos. Sustituye al anterior."""
    sede = _sede(db)
    anterior = db.get(Archivo, sede.logo_archivo_id) if sede.logo_archivo_id else None
    nuevo = almacen.guardar(db, archivo, usuario, tipos=almacen.IMAGENES)
    sede.logo_archivo_id = nuevo.id
    db.flush()
    if anterior is not None:
        almacen.descartar(db, anterior)
    db.commit()
    db.refresh(sede)
    return sede


@router.delete("/catalogos/clinica/logo", status_code=status.HTTP_204_NO_CONTENT)
def quitar_logo(db: BD, _: SoloAdmin) -> Response:
    sede = _sede(db)
    anterior = db.get(Archivo, sede.logo_archivo_id) if sede.logo_archivo_id else None
    sede.logo_archivo_id = None
    db.flush()
    if anterior is not None:
        almacen.descartar(db, anterior)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Especialidades ------------------------------------------------------------


def _especialidad(db: Session, especialidad_id: int) -> Especialidad:
    especialidad = db.get(Especialidad, especialidad_id)
    if especialidad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La especialidad no existe")
    return especialidad


def _usos_especialidad(db: Session) -> tuple[dict[int, int], dict[int, int]]:
    planes = dict(
        db.execute(
            select(PlanTratamiento.especialidad_id, func.count())
            .where(PlanTratamiento.especialidad_id.is_not(None))
            .group_by(PlanTratamiento.especialidad_id)
        ).all()
    )
    doctores = dict(
        db.execute(
            select(DoctorEspecialidad.especialidad_id, func.count()).group_by(
                DoctorEspecialidad.especialidad_id
            )
        ).all()
    )
    return planes, doctores


def _especialidad_leer(db: Session, especialidad: Especialidad) -> EspecialidadLeer:
    planes, doctores = _usos_especialidad(db)
    return EspecialidadLeer.model_validate(especialidad).model_copy(
        update={
            "planes": planes.get(especialidad.id, 0),
            "doctores": doctores.get(especialidad.id, 0),
        }
    )


def _exigir_especialidad_libre(db: Session, nombre: str, excepto: int | None = None) -> None:
    duplicada = db.scalar(
        select(Especialidad.id).where(
            func.lower(Especialidad.nombre) == nombre.strip().lower(),
            Especialidad.id != (excepto or 0),
        )
    )
    if duplicada is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe la especialidad «{nombre}»")


@router.get("/especialidades", response_model=list[EspecialidadLeer])
def listar_especialidades(
    db: BD, _: UsuarioAuth, incluir_inactivas: bool = False
) -> list[EspecialidadLeer]:
    consulta = select(Especialidad).order_by(Especialidad.nombre)
    if not incluir_inactivas:
        consulta = consulta.where(Especialidad.activo)

    planes, doctores = _usos_especialidad(db)
    return [
        EspecialidadLeer.model_validate(e).model_copy(
            update={"planes": planes.get(e.id, 0), "doctores": doctores.get(e.id, 0)}
        )
        for e in db.scalars(consulta)
    ]


@router.post(
    "/especialidades", response_model=EspecialidadLeer, status_code=status.HTTP_201_CREATED
)
def crear_especialidad(datos: EspecialidadCrear, db: BD, _: SoloAdmin) -> EspecialidadLeer:
    _exigir_especialidad_libre(db, datos.nombre)
    if datos.codigo and db.scalar(
        select(Especialidad.id).where(Especialidad.codigo == datos.codigo)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe el código {datos.codigo}")

    especialidad = Especialidad(
        nombre=datos.nombre.strip(),
        descripcion=datos.descripcion,
        codigo=datos.codigo or codigo_desde_nombre(db, Especialidad, datos.nombre),
        activo=True,
    )
    db.add(especialidad)
    db.commit()
    db.refresh(especialidad)
    return _especialidad_leer(db, especialidad)


@router.patch("/especialidades/{especialidad_id}", response_model=EspecialidadLeer)
def actualizar_especialidad(
    especialidad_id: int, datos: EspecialidadActualizar, db: BD, _: SoloAdmin
) -> EspecialidadLeer:
    especialidad = _especialidad(db, especialidad_id)
    cambios = datos.model_dump(exclude_unset=True)

    if cambios.get("nombre"):
        _exigir_especialidad_libre(db, cambios["nombre"], excepto=especialidad_id)
        especialidad.nombre = cambios["nombre"].strip()
    if "descripcion" in cambios:
        especialidad.descripcion = cambios["descripcion"]
    if cambios.get("activo") is not None:
        especialidad.activo = cambios["activo"]

    db.commit()
    db.refresh(especialidad)
    return _especialidad_leer(db, especialidad)


@router.delete("/especialidades/{especialidad_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_especialidad(especialidad_id: int, db: BD, _: SoloAdmin) -> None:
    especialidad = _especialidad(db, especialidad_id)
    planes, doctores = _usos_especialidad(db)
    if planes.get(especialidad_id) or doctores.get(especialidad_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La especialidad tiene planes o doctores: desactívala en lugar de borrarla",
        )
    db.delete(especialidad)
    db.commit()


# --- Unidades dentales ---------------------------------------------------------


def _unidad(db: Session, unidad_id: int) -> UnidadDental:
    unidad = db.get(UnidadDental, unidad_id)
    if unidad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La unidad dental no existe")
    return unidad


def _exigir_unidad_libre(
    db: Session, sede_id: int, nombre: str, excepto: int | None = None
) -> None:
    duplicada = db.scalar(
        select(UnidadDental.id).where(
            UnidadDental.sede_id == sede_id,
            func.lower(UnidadDental.nombre) == nombre.strip().lower(),
            UnidadDental.id != (excepto or 0),
        )
    )
    if duplicada is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe la unidad «{nombre}»")


@router.get("/unidades", response_model=list[UnidadLeer])
def listar_unidades(db: BD, _: UsuarioAuth, incluir_inactivas: bool = False) -> list[UnidadDental]:
    consulta = select(UnidadDental).order_by(UnidadDental.orden, UnidadDental.nombre)
    if not incluir_inactivas:
        consulta = consulta.where(UnidadDental.activo)
    return list(db.scalars(consulta))


@router.post("/unidades", response_model=UnidadLeer, status_code=status.HTTP_201_CREATED)
def crear_unidad(datos: UnidadCrear, db: BD, _: SoloAdmin) -> UnidadDental:
    sede_id = datos.sede_id or db.scalar(select(func.min(Sede.id)).where(Sede.activo))
    if sede_id is None or db.get(Sede, sede_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La sede no existe")
    _exigir_unidad_libre(db, sede_id, datos.nombre)

    unidad = UnidadDental(
        sede_id=sede_id,
        nombre=datos.nombre.strip(),
        alquilada=datos.alquilada,
        orden=datos.orden,
        activo=True,
    )
    db.add(unidad)
    db.commit()
    db.refresh(unidad)
    return unidad


@router.patch("/unidades/{unidad_id}", response_model=UnidadLeer)
def actualizar_unidad(
    unidad_id: int, datos: UnidadActualizar, db: BD, _: SoloAdmin
) -> UnidadDental:
    unidad = _unidad(db, unidad_id)
    cambios = {k: v for k, v in datos.model_dump(exclude_unset=True).items() if v is not None}

    if "nombre" in cambios:
        _exigir_unidad_libre(db, unidad.sede_id, cambios["nombre"], excepto=unidad_id)
        cambios["nombre"] = cambios["nombre"].strip()
    for campo, valor in cambios.items():
        setattr(unidad, campo, valor)

    db.commit()
    db.refresh(unidad)
    return unidad


@router.delete("/unidades/{unidad_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_unidad(unidad_id: int, db: BD, _: SoloAdmin) -> None:
    unidad = _unidad(db, unidad_id)
    usada = db.scalar(select(Cita.id).where(Cita.unidad_id == unidad_id).limit(1)) or db.scalar(
        select(Consulta.id).where(Consulta.unidad_id == unidad_id).limit(1)
    )
    if usada:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La unidad tiene citas o consultas: desactívala en lugar de borrarla",
        )
    db.delete(unidad)
    db.commit()


# --- Doctores ------------------------------------------------------------------


def _doctor(db: Session, doctor_id: int) -> Doctor:
    doctor = db.scalar(
        select(Doctor).where(Doctor.id == doctor_id).options(selectinload(Doctor.especialidades))
    )
    if doctor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El doctor no existe")
    return doctor


def _doctor_leer(doctor: Doctor) -> DoctorLeer:
    return DoctorLeer(
        id=doctor.id,
        documento=doctor.documento,
        nombres=doctor.nombres,
        apellidos=doctor.apellidos,
        nombre_completo=doctor.nombre_completo,
        licencia=doctor.licencia,
        email=doctor.email,
        telefono=doctor.telefono,
        porcentaje_comision=doctor.porcentaje_comision,
        activo=doctor.activo,
        especialidades=[
            DoctorEspecialidadLeer(
                especialidad_id=de.especialidad_id,
                nombre=de.especialidad.nombre,
                principal=de.principal,
            )
            for de in sorted(doctor.especialidades, key=lambda de: not de.principal)
        ],
    )


def _exigir_doctor_unico(
    db: Session, campo: str, valor: str | None, excepto: int | None = None
) -> None:
    """documento, licencia y email son UNIQUE: se comprueba antes para dar un
    mensaje que diga cuál choca."""
    if not valor:
        return
    duplicado = db.scalar(
        select(Doctor.id).where(getattr(Doctor, campo) == valor, Doctor.id != (excepto or 0))
    )
    if duplicado is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe un doctor con {campo} {valor}")


def _asignar_especialidades(db: Session, doctor: Doctor, ids: list[int]) -> None:
    """Reemplaza las especialidades del doctor. La primera queda como principal."""
    ids = list(dict.fromkeys(ids))
    existentes = set(db.scalars(select(Especialidad.id).where(Especialidad.id.in_(ids))))
    faltan = [i for i in ids if i not in existentes]
    if faltan:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"especialidad_ids: no existen {faltan}"
        )

    actuales = {de.especialidad_id: de for de in doctor.especialidades}
    for especialidad_id in list(actuales):
        if especialidad_id not in ids:
            doctor.especialidades.remove(actuales[especialidad_id])
    for posicion, especialidad_id in enumerate(ids):
        if especialidad_id in actuales:
            actuales[especialidad_id].principal = posicion == 0
        else:
            doctor.especialidades.append(
                DoctorEspecialidad(especialidad_id=especialidad_id, principal=posicion == 0)
            )


@router.get("/doctores", response_model=list[DoctorLeer])
def listar_doctores(db: BD, _: UsuarioAuth, incluir_inactivos: bool = False) -> list[DoctorLeer]:
    consulta = (
        select(Doctor)
        .options(selectinload(Doctor.especialidades))
        .order_by(Doctor.apellidos, Doctor.nombres)
    )
    if not incluir_inactivos:
        consulta = consulta.where(Doctor.activo)
    return [_doctor_leer(d) for d in db.scalars(consulta)]


@router.post("/doctores", response_model=DoctorLeer, status_code=status.HTTP_201_CREATED)
def crear_doctor(datos: DoctorCrear, db: BD, _: SoloAdmin) -> DoctorLeer:
    for campo in ("documento", "licencia", "email"):
        _exigir_doctor_unico(db, campo, getattr(datos, campo))

    doctor = Doctor(
        **datos.model_dump(exclude={"especialidad_ids"}),
        sede_id=db.scalar(select(func.min(Sede.id)).where(Sede.activo)),
        activo=True,
    )
    db.add(doctor)
    db.flush()
    _asignar_especialidades(db, doctor, datos.especialidad_ids)
    db.commit()
    return _doctor_leer(_doctor(db, doctor.id))


@router.patch("/doctores/{doctor_id}", response_model=DoctorLeer)
def actualizar_doctor(doctor_id: int, datos: DoctorActualizar, db: BD, _: SoloAdmin) -> DoctorLeer:
    doctor = _doctor(db, doctor_id)
    cambios = datos.model_dump(exclude_unset=True, exclude={"especialidad_ids"})

    for campo in ("documento", "licencia", "email"):
        if campo in cambios:
            _exigir_doctor_unico(db, campo, cambios[campo], excepto=doctor_id)

    anulables = {"licencia", "email", "telefono"}
    for campo, valor in cambios.items():
        if valor is None and campo not in anulables:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"{campo}: no puede quedar vacío"
            )
        setattr(doctor, campo, valor)

    if datos.especialidad_ids is not None:
        _asignar_especialidades(db, doctor, datos.especialidad_ids)

    db.commit()
    return _doctor_leer(_doctor(db, doctor_id))
