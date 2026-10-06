"""Agregador de routers de la v1."""

from fastapi import APIRouter

from app.api.v1.routers import (
    archivos,
    auth,
    catalogos,
    citas,
    clinica,
    cuenta,
    documentos,
    ficha,
    fiscal,
    historial,
    implantes,
    informes,
    inventario,
    odontograma,
    onboarding,
    pacientes,
    resumen,
    servicios,
    usuarios,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(catalogos.router)
api_router.include_router(pacientes.router)
api_router.include_router(ficha.router)
api_router.include_router(odontograma.router)
api_router.include_router(citas.router)
api_router.include_router(historial.router)
api_router.include_router(cuenta.router)
api_router.include_router(documentos.router)
api_router.include_router(inventario.router)
api_router.include_router(archivos.router)
api_router.include_router(implantes.router)
api_router.include_router(fiscal.router)
api_router.include_router(resumen.router)
api_router.include_router(informes.router)
api_router.include_router(onboarding.router)
api_router.include_router(servicios.router)
api_router.include_router(clinica.router)
api_router.include_router(usuarios.router)
