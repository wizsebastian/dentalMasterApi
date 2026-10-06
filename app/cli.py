"""Comandos de mantenimiento. Uso: python -m app.cli <comando>"""

import os
import sys
from getpass import getpass

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import select, update

from app.core.security import hash_password, revisar_password
from app.db.session import SessionLocal, engine
from app.models.enums import RolUsuario
from app.models.organizacion import Sede, Usuario

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


def pedir_password() -> str:
    """Pide la contraseña dos veces por consola y la valida."""
    password = getpass("Contraseña: ")

    motivo = revisar_password(password)
    if motivo:
        print(f"Contraseña rechazada: {motivo}", file=sys.stderr)
        raise SystemExit(1)

    if password != getpass("Repetir: "):
        print("Las contraseñas no coinciden", file=sys.stderr)
        raise SystemExit(1)

    return password


def cambiar_password() -> None:
    """Rota la contraseña de un usuario existente.

    python -m app.cli cambiar-password <email>
    """
    if len(sys.argv) < 3:
        print("uso: python -m app.cli cambiar-password <email>", file=sys.stderr)
        raise SystemExit(2)

    email = sys.argv[2].strip().lower()

    with SessionLocal() as db:
        usuario = db.scalar(select(Usuario).where(Usuario.email == email))
        if usuario is None:
            print(f"No existe ningún usuario con el email {email}", file=sys.stderr)
            raise SystemExit(1)

        usuario.password_hash = hash_password(pedir_password())
        db.commit()

    print(f"[cli] contraseña de {email} actualizada")


def crear_usuario() -> None:
    """Da de alta un usuario real. Uso:

        python -m app.cli crear-usuario <email> <rol> [doctor_id]

    Es la única vía de entrada en producción, donde `seed-users` no corre. La
    contraseña se pide por consola para que no quede en el historial del shell.
    """
    if len(sys.argv) < 4:
        print(
            "uso: python -m app.cli crear-usuario <email> "
            f"<{'|'.join(r.value for r in RolUsuario)}> [doctor_id]",
            file=sys.stderr,
        )
        raise SystemExit(2)

    email = sys.argv[2].strip().lower()
    try:
        rol = RolUsuario(sys.argv[3])
    except ValueError:
        print(f"rol inválido: {sys.argv[3]}", file=sys.stderr)
        raise SystemExit(2) from None

    doctor_id = int(sys.argv[4]) if len(sys.argv) > 4 else None

    password = pedir_password()

    with SessionLocal() as db:
        if db.scalar(select(Usuario).where(Usuario.email == email)):
            print(f"Ya existe un usuario con el email {email}", file=sys.stderr)
            raise SystemExit(1)

        db.add(
            Usuario(
                email=email,
                password_hash=hash_password(password),
                rol=rol,
                doctor_id=doctor_id,
                activo=True,
            )
        )
        db.commit()

    print(f"[cli] usuario {email} creado con rol {rol}")


def iniciar_clinica() -> None:
    """Prepara una base vacía para empezar a trabajar. Uso:

        python -m app.cli iniciar-clinica <email-del-administrador> ["Nombre de la clínica"]

    Crea la sede (sin ella no hay clínica que poner en los impresos) y el primer
    administrador; el resto —doctores, usuarios, unidades— se crea desde la
    aplicación. La contraseña se pide por consola, o se toma de la variable
    `PASSWORD_INICIAL` para poder preparar una base de pruebas sin teclado.
    """
    if len(sys.argv) < 3:
        print(
            'uso: python -m app.cli iniciar-clinica <email> ["Nombre de la clínica"]',
            file=sys.stderr,
        )
        raise SystemExit(2)

    email = sys.argv[2].strip().lower()
    nombre = sys.argv[3].strip() if len(sys.argv) > 3 else "Mi clínica"

    password = os.environ.get("PASSWORD_INICIAL") or pedir_password()
    motivo = revisar_password(password)
    if motivo:
        print(f"Contraseña rechazada: {motivo}", file=sys.stderr)
        raise SystemExit(1)

    with SessionLocal() as db:
        if db.scalar(select(Usuario).where(Usuario.email == email)):
            print(f"Ya existe un usuario con el email {email}", file=sys.stderr)
            raise SystemExit(1)
        if db.scalar(select(Sede.id).limit(1)) is None:
            db.add(Sede(nombre=nombre))
        db.add(
            Usuario(
                email=email,
                password_hash=hash_password(password),
                rol=RolUsuario.ADMIN,
                activo=True,
            )
        )
        db.commit()

    print(f"[cli] clínica «{nombre}» lista; administrador {email}")


COMMANDS = {
    "db-baseline": db_baseline,
    "seed-users": seed_users,
    "crear-usuario": crear_usuario,
    "iniciar-clinica": iniciar_clinica,
    "cambiar-password": cambiar_password,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"uso: python -m app.cli {{{'|'.join(COMMANDS)}}}", file=sys.stderr)
        return 2
    COMMANDS[sys.argv[1]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
