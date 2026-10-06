"""La guía de primeros pasos: cómo va la configuración de una clínica nueva.

El progreso **se calcula**, no se marca: «hay un doctor» es un hecho de la base.
Así no puede quedar desincronizado, y un paso se completa solo cuando el cliente
hace el trabajo real. Sólo lo que no deja rastro («revisé mis precios») se guarda
como marca en la sede.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cuenta import SecuenciaNcf
from app.models.enums import RolUsuario
from app.models.organizacion import Doctor, Sede, UnidadDental, Usuario
from app.schemas.onboarding import OnboardingLeer, PasoLeer

# El nombre con el que nace la clínica (`iniciar-clinica`): mientras no cambie, no
# se ha puesto el de verdad.
NOMBRE_INICIAL = "Mi clínica"


def sede_principal(db: Session) -> Sede | None:
    return db.scalar(select(Sede).where(Sede.activo).order_by(Sede.id))


def _hay(db: Session, consulta) -> bool:
    return (db.scalar(select(func.count()).select_from(consulta.subquery())) or 0) > 0


def estado(db: Session, *, detalle: bool = True) -> OnboardingLeer:
    sede = sede_principal(db)
    if sede is None:
        # Sin sede no hay nada que configurar desde la aplicación.
        return OnboardingLeer(listo=False, cerrado=False)

    clinica_lista = bool(
        sede.nombre.strip()
        and sede.nombre.strip() != NOMBRE_INICIAL
        and (sede.telefono or "").strip()
    )
    pasos = [
        PasoLeer(
            id="clinica", titulo="Datos de tu clínica y logo", obligatorio=True, hecho=clinica_lista
        ),
        PasoLeer(
            id="doctores",
            titulo="Tus doctores",
            obligatorio=True,
            hecho=_hay(db, select(Doctor.id).where(Doctor.activo)),
        ),
        PasoLeer(
            id="unidades",
            titulo="Unidades dentales (sillones)",
            obligatorio=False,
            hecho=_hay(db, select(UnidadDental.id).where(UnidadDental.activo)),
        ),
        PasoLeer(
            id="equipo",
            titulo="Tu equipo",
            obligatorio=False,
            hecho=_hay(
                db, select(Usuario.id).where(Usuario.rol != RolUsuario.ADMIN, Usuario.activo)
            ),
        ),
        PasoLeer(
            id="ncf",
            titulo="Comprobantes fiscales (NCF)",
            obligatorio=False,
            hecho=_hay(db, select(SecuenciaNcf.id).where(SecuenciaNcf.activo)),
        ),
        PasoLeer(
            id="catalogo",
            titulo="Revisa tus servicios y precios",
            obligatorio=False,
            hecho=sede.catalogo_revisado_en is not None,
        ),
    ]
    listo = all(p.hecho for p in pasos if p.obligatorio)
    cerrado = sede.onboarding_cerrado_en is not None

    if not detalle:
        return OnboardingLeer(listo=listo, cerrado=cerrado)
    return OnboardingLeer(
        pasos=pasos,
        hechos=sum(p.hecho for p in pasos),
        total=len(pasos),
        listo=listo,
        cerrado=cerrado,
    )
