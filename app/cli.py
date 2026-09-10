"""Comandos de mantenimiento. Uso: python -m app.cli <comando>"""

import sys

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import select, update

from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models.organizacion import Usuario

# Contraseña única para todos los usuarios del seed demo. Sólo desarrollo:
# el entrypoint sólo ejecuta seed-users cuando SEED_DEMO_USERS=true.
DEMO_PASSWORD = "dental2026"

# Revisión que representa el esquema creado por db/init/*.sql
BASELINE_REVISION = "0001_baseline"


def db_baseline() -> None:
    """Alinea Alembic con el esquema que crearon los .sql de db/init.

    Los .sql son la fuente de verdad del esquema inicial, así que la primera vez
    Alembic sólo *marca* ese estado como baseline en lugar de aplicar
    migraciones. A partir de ahí, `upgrade head` es lo normal.
    """
    cfg = Config("alembic.ini")
    with engine.connect() as conn:
        version = MigrationContext.configure(conn).get_current_revision()

    if version is None:
        # Base recién creada por los .sql: se ancla en el baseline, no en head,
        # para que cualquier migración posterior sí se aplique a continuación.
        print(f"[cli] sin alembic_version: anclando en {BASELINE_REVISION}")
        command.stamp(cfg, BASELINE_REVISION)

    print("[cli] aplicando migraciones pendientes")
    command.upgrade(cfg, "head")


def seed_users() -> None:
    """Sustituye los password_hash marcadores del seed por hashes bcrypt reales.

    `03_seed_demo.sql` inserta el literal '$2b$12$CAMBIAR_ESTE_HASH_EN_PRODUCCION',
    que no es un hash válido: sin este paso nadie puede iniciar sesión.
    """
    nuevo = hash_password(DEMO_PASSWORD)
    with SessionLocal() as db:
        pendientes = db.scalars(
            select(Usuario.email).where(Usuario.password_hash.like("%CAMBIAR%"))
        ).all()
        if not pendientes:
            print("[cli] sin hashes marcadores pendientes")
            return
        db.execute(
            update(Usuario)
            .where(Usuario.password_hash.like("%CAMBIAR%"))
            .values(password_hash=nuevo)
        )
        db.commit()
    print(f"[cli] {len(pendientes)} usuarios con contraseña '{DEMO_PASSWORD}':")
    for email in pendientes:
        print(f"       - {email}")


COMMANDS = {"db-baseline": db_baseline, "seed-users": seed_users}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"uso: python -m app.cli {{{'|'.join(COMMANDS)}}}", file=sys.stderr)
        return 2
    COMMANDS[sys.argv[1]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
