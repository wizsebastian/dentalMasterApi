"""Punto de entrada de la API de DentalMaster."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import engine

app = FastAPI(
    title=settings.app_name,
    description="Gestión clínica odontológica: pacientes, ficha médica y odontograma FDI.",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["infra"])
def health() -> dict[str, object]:
    """Comprueba que la API responde y que la base está accesible y poblada."""
    with engine.connect() as conn:
        dientes = conn.execute(text("SELECT count(*) FROM diente")).scalar_one()
    return {"status": "ok", "dientes_en_catalogo": dientes}
