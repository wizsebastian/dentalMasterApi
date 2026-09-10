"""Catálogos maestros que alimentan el odontograma.

Datos de solo lectura que no cambian durante una sesión: el frontend los pide
una vez y los cachea.
"""

from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import BD, UsuarioAuth
from app.models.catalogo import Alergia, CondicionDental, CondicionMedica, Diente, Superficie
from app.schemas.odontograma import (
    Catalogos,
    CondicionDentalLeer,
    DienteLeer,
    SuperficieLeer,
)

router = APIRouter(prefix="/catalogos", tags=["catálogos"])


@router.get("/odontograma", response_model=Catalogos)
def catalogos_odontograma(db: BD, _: UsuarioAuth) -> Catalogos:
    """Piezas, caras y condiciones en una sola llamada.

    Van juntas porque el odontograma no puede dibujarse sin las tres, y pedirlas
    por separado sólo añade viajes.
    """
    dientes = db.scalars(select(Diente).order_by(Diente.cuadrante, Diente.posicion)).all()
    superficies = db.scalars(select(Superficie).order_by(Superficie.codigo)).all()
    condiciones = db.scalars(
        select(CondicionDental).order_by(CondicionDental.orden, CondicionDental.codigo)
    ).all()

    return Catalogos(
        dientes=[DienteLeer.model_validate(d) for d in dientes],
        superficies=[SuperficieLeer.model_validate(s) for s in superficies],
        condiciones=[CondicionDentalLeer.model_validate(c) for c in condiciones],
    )


@router.get("/condiciones-medicas")
def condiciones_medicas(db: BD, _: UsuarioAuth) -> list[dict]:
    """Antecedentes sistémicos, para el formulario de la ficha médica."""
    filas = db.scalars(select(CondicionMedica).order_by(CondicionMedica.nombre)).all()
    return [
        {"id": c.id, "codigo": c.codigo, "nombre": c.nombre, "riesgo": c.riesgo, "alerta": c.alerta}
        for c in filas
    ]


@router.get("/alergias")
def alergias(db: BD, _: UsuarioAuth) -> list[dict]:
    filas = db.scalars(select(Alergia).order_by(Alergia.nombre)).all()
    return [{"id": a.id, "codigo": a.codigo, "nombre": a.nombre, "tipo": a.tipo} for a in filas]
