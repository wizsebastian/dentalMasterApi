"""Piezas compartidas por varios schemas."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Pagina(BaseModel, Generic[T]):
    """Respuesta paginada."""

    items: list[T]
    total: int = Field(description="Total de resultados que cumplen el filtro")
    limite: int
    offset: int
