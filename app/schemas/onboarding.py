"""Schemas de la guía de primeros pasos."""

from pydantic import BaseModel, Field


class PasoLeer(BaseModel):
    id: str
    titulo: str
    obligatorio: bool
    hecho: bool


class OnboardingLeer(BaseModel):
    """Cómo va la configuración de la clínica.

    Quien no es administración recibe sólo `listo` y `cerrado` (`pasos` vacío):
    le basta para saber si la clínica está lista, sin enseñarle conteos internos.
    """

    pasos: list[PasoLeer] = []
    hechos: int = 0
    total: int = 0
    listo: bool = Field(description="Lo mínimo para trabajar está hecho")
    cerrado: bool = Field(description="La guía se terminó u omitió y ya no se ofrece")
