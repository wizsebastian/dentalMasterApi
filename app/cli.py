"""Comandos de mantenimiento. Uso: python -m app.cli <comando>"""

import sys
from getpass import getpass

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import select, update

from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models.enums import RolUsuario
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


MIN_PASSWORD = 12


def revisar_password(password: str) -> str | None:
    """Devuelve el motivo de rechazo, o None si la contraseña es aceptable.

    La longitud sola no basta: '12345678912345' tiene catorce caracteres y se
    adivina al primer intento. Se rechazan secuencias, repeticiones y patrones
    de teclado, que es justo lo que se escribe cuando el único requisito es un
    mínimo de longitud.
    """
    if len(password) < MIN_PASSWORD:
        return f"debe tener al menos {MIN_PASSWORD} caracteres"

    if len(set(password)) < 5:
        return "usa muy pocos caracteres distintos"

    minuscula = password.lower()

    for base in ("0123456789", "abcdefghijklmnopqrstuvwxyz"):
        for referencia in (base, base[::-1]):
            for inicio in range(len(referencia) - 5):
                if referencia[inicio : inicio + 6] in minuscula:
                    return "contiene una secuencia previsible (12345…, abcde…)"

    for patron in ("qwerty", "asdfgh", "password", "contrasena", "dental", "admin"):
        if patron in minuscula:
            return f"contiene un patrón previsible ({patron})"

    if password.isdigit():
        return "no puede ser sólo dígitos"

    return None


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


COMMANDS = {
    "db-baseline": db_baseline,
    "seed-users": seed_users,
    "crear-usuario": crear_usuario,
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
