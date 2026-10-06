"""Punto de entrada de la API de DentalMaster."""

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import engine

app = FastAPI(
    title=settings.app_name,
    description=(
        "Gestión clínica odontológica: pacientes, ficha médica, odontograma FDI, "
        "catálogo de servicios y configuración de la clínica."
    ),
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

# Violaciones que la base rechaza y que ningún router comprobó antes. Los routers
# siguen validando lo previsible para dar un mensaje preciso; esto es la red que
# evita un 500 cuando dos peticiones compiten por el mismo hueco o el mismo código.
_CONFLICTOS = {
    "ex_cita_doctor": "El doctor ya tiene una cita en ese horario",
    "ex_cita_unidad": "La unidad dental ya está ocupada en ese horario",
}
_POR_SQLSTATE = {
    "23505": "Ya existe un registro con esos datos",
    "23P01": "Se solapa con un registro existente",
    "23503": "El registro está en uso o hace referencia a algo que no existe",
}


@app.exception_handler(IntegrityError)
def conflicto_de_integridad(_: Request, exc: IntegrityError) -> JSONResponse:
    original = exc.orig
    restriccion = getattr(getattr(original, "diag", None), "constraint_name", None)
    detalle = _CONFLICTOS.get(restriccion or "") or _POR_SQLSTATE.get(
        getattr(original, "sqlstate", "") or "", "La operación viola una regla de integridad"
    )
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": detalle})


@app.get("/health", tags=["infra"])
def health() -> dict[str, object]:
    """Comprueba que la API responde y que la base está accesible y poblada."""
    with engine.connect() as conn:
        dientes = conn.execute(text("SELECT count(*) FROM diente")).scalar_one()
    return {"status": "ok", "dientes_en_catalogo": dientes}
