"""Numeración sin huecos ni carreras: expedientes, planes, recibos y códigos.

Cada serie es una fila de `correlativo`. Avanzarla con INSERT … ON CONFLICT
bloquea la fila hasta que termina la transacción: dos altas simultáneas se
serializan en lugar de chocar contra el UNIQUE, y un rollback devuelve el
número, de modo que no quedan huecos.
"""

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

_AVANZAR = text(
    "INSERT INTO correlativo (clave, ultimo) VALUES (:clave, :minimo + 1) "
    "ON CONFLICT (clave) DO UPDATE "
    "SET ultimo = GREATEST(correlativo.ultimo, :minimo) + 1 "
    "RETURNING ultimo"
)


def siguiente(db: Session, clave: str, *, minimo: int = 0) -> int:
    """Consume y devuelve el siguiente número de la serie `clave`.

    `minimo` es el mayor número que ya existe en la tabla destino. Sólo importa
    cuando la serie no tiene fila o quedó por detrás (una base cargada a mano):
    con él la serie se pone al día sola en lugar de repetir un número.
    """
    return db.execute(_AVANZAR, {"clave": clave, "minimo": minimo}).scalar_one()


def _mayor_sufijo(db: Session, tabla: str, columna: str, prefijo: str) -> int:
    """Mayor número ya usado tras `prefijo`, comparado como número y no como texto."""
    # `tabla` y `columna` son constantes de este módulo, nunca entrada del usuario.
    fila = db.execute(
        text(
            f"SELECT COALESCE(MAX(substr({columna}, :desde)::int), 0) FROM {tabla} "  # noqa: S608
            f"WHERE {columna} ~ :patron"
        ),
        {"desde": len(prefijo) + 1, "patron": f"^{prefijo}[0-9]+$"},
    ).scalar_one()
    return int(fila)


def codigo_expediente(db: Session) -> str:
    """PAC-2026-0001. La serie reinicia cada año."""
    anio = datetime.now(UTC).year
    prefijo = f"PAC-{anio}-"
    numero = siguiente(
        db, f"paciente:{anio}", minimo=_mayor_sufijo(db, "paciente", "codigo", prefijo)
    )
    return f"{prefijo}{numero:04d}"


def codigo_plan(db: Session) -> str:
    """PT-2026-0001. La serie reinicia cada año."""
    anio = datetime.now(UTC).year
    prefijo = f"PT-{anio}-"
    numero = siguiente(
        db, f"plan:{anio}", minimo=_mayor_sufijo(db, "plan_tratamiento", "codigo", prefijo)
    )
    return f"{prefijo}{numero:04d}"


def codigo_servicio(db: Session, codigo_categoria: str) -> str:
    """REST-012: código de la categoría más un consecutivo propio de ella."""
    prefijo = f"{codigo_categoria}-"
    numero = siguiente(
        db,
        f"servicio:{codigo_categoria}",
        minimo=_mayor_sufijo(db, "servicio", "codigo", prefijo),
    )
    return f"{prefijo}{numero:03d}"


def numero_recibo(db: Session) -> int:
    """Recibo de pago. Serie única, sin reinicio."""
    return siguiente(db, "recibo")
