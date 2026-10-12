"""Guía interactiva del sistema: sesiones, respuestas y bitácora de cambios.

Revision ID: 0002_guia
Revises: 0001_baseline
Create Date: 2026-10-12

Primera migración incremental. Guarda lo que quien prueba el sistema marca y
escribe en `/guia` (vista pública, sin sesión). No toca el dominio clínico.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_guia"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE guia_sesion (
            id                 BIGSERIAL PRIMARY KEY,
            codigo             TEXT NOT NULL UNIQUE,
            nombre             TEXT NOT NULL CHECK (char_length(nombre) BETWEEN 2 AND 120),
            rol                TEXT CHECK (char_length(rol) <= 60),
            impresion_general  TEXT NOT NULL DEFAULT ''
                               CHECK (char_length(impresion_general) <= 8000),
            creado_en          TIMESTAMPTZ NOT NULL DEFAULT now(),
            actualizado_en     TIMESTAMPTZ NOT NULL DEFAULT now(),
            ip                 INET,
            dispositivo        TEXT
        );

        CREATE TABLE guia_respuesta (
            sesion_id       BIGINT NOT NULL REFERENCES guia_sesion(id) ON DELETE CASCADE,
            paso_id         TEXT NOT NULL CHECK (paso_id ~ '^[a-z0-9][a-z0-9_-]{0,39}$'),
            estado          TEXT NOT NULL DEFAULT '' CHECK (estado IN ('', 'ok', 'falla', 'duda')),
            nota            TEXT NOT NULL DEFAULT '' CHECK (char_length(nota) <= 4000),
            actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (sesion_id, paso_id)
        );

        -- Sólo inserción: cada cambio queda, para ver el recorrido y no sólo el final.
        CREATE TABLE guia_evento (
            id         BIGSERIAL PRIMARY KEY,
            sesion_id  BIGINT NOT NULL REFERENCES guia_sesion(id) ON DELETE CASCADE,
            paso_id    TEXT NOT NULL,
            estado     TEXT NOT NULL,
            nota       TEXT NOT NULL,
            creado_en  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_guia_evento_sesion ON guia_evento (sesion_id, creado_en);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE guia_evento; DROP TABLE guia_respuesta; DROP TABLE guia_sesion;")
