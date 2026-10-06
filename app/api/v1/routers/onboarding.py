"""Guía de primeros pasos para una clínica recién entregada."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import BD, UsuarioAuth, requiere_rol
from app.models.enums import RolUsuario
from app.models.organizacion import Usuario
from app.schemas.onboarding import OnboardingLeer
from app.services import onboarding

router = APIRouter(tags=["primeros pasos"])

SoloAdmin = Annotated[Usuario, Depends(requiere_rol())]


def _sede(db: BD):
    sede = onboarding.sede_principal(db)
    if sede is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No hay ninguna sede registrada")
    return sede


@router.get("/onboarding", response_model=OnboardingLeer)
def estado(db: BD, usuario: UsuarioAuth) -> OnboardingLeer:
    """Cómo va la configuración. El detalle es sólo de administración: el resto
    sólo necesita saber si la clínica está lista."""
    return onboarding.estado(db, detalle=usuario.rol == RolUsuario.ADMIN)


@router.post("/onboarding/revisar-catalogo", response_model=OnboardingLeer)
def revisar_catalogo(db: BD, _: SoloAdmin) -> OnboardingLeer:
    """«Ya revisé mis servicios y precios»: el único paso sin dato observable."""
    sede = _sede(db)
    if sede.catalogo_revisado_en is None:
        sede.catalogo_revisado_en = datetime.now(UTC)
        db.commit()
    return onboarding.estado(db)


@router.post("/onboarding/cerrar", response_model=OnboardingLeer)
def cerrar(db: BD, _: SoloAdmin) -> OnboardingLeer:
    """Termina la guía. No se puede omitir: exige lo obligatorio (los datos de la
    clínica y un doctor), porque una clínica a medias no está lista para trabajar."""
    sede = _sede(db)
    if not onboarding.estado(db).listo:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Faltan pasos obligatorios: los datos de la clínica y al menos un doctor",
        )
    if sede.onboarding_cerrado_en is None:
        sede.onboarding_cerrado_en = datetime.now(UTC)
        db.commit()
    return onboarding.estado(db)
