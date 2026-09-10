"""Agregador de routers de la v1."""

from fastapi import APIRouter

from app.api.v1.routers import auth, catalogos, ficha, odontograma, pacientes

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(catalogos.router)
api_router.include_router(pacientes.router)
api_router.include_router(ficha.router)
api_router.include_router(odontograma.router)
