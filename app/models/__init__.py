"""Modelos SQLAlchemy.

El esquema lo definen los .sql de `db/init/`; estos modelos lo mapean, no lo
generan. Cualquier cambio estructural se hace primero en una migración de
Alembic y después aquí.
"""

from app.models.base import Base

__all__ = ["Base"]
