"""Baseline: el esquema que crean los .sql de db/init.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-10

Esta revisión no crea nada. Representa el estado que dejan 01_schema.sql,
02_seed_catalogos.sql y (en desarrollo) 03_seed_demo.sql al ejecutarse en el
initdb.d de Postgres. Existe para que Alembic tenga un punto de anclaje del que
colgar las migraciones incrementales; `app.cli db-baseline` la marca con `stamp`
en una base recién creada.
"""

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    raise NotImplementedError("El baseline no se revierte: se recrea la base desde los .sql")
