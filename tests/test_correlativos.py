"""Numeración de expedientes, planes, recibos y códigos de servicio."""

from datetime import UTC, datetime

from app.services import correlativos

ANIO = datetime.now(UTC).year


def test_la_serie_avanza_de_uno_en_uno(db):
    primero = correlativos.siguiente(db, "prueba")
    segundo = correlativos.siguiente(db, "prueba")
    assert (primero, segundo) == (1, 2)


def test_un_rollback_devuelve_el_numero(db):
    """Sin huecos: el número consumido en una transacción fallida se reutiliza."""
    antes = correlativos.numero_recibo(db)
    punto = db.begin_nested()
    correlativos.numero_recibo(db)
    punto.rollback()

    assert correlativos.numero_recibo(db) == antes + 1


def test_una_serie_atrasada_se_pone_al_dia(db, sql):
    """Una base cargada a mano puede traer la serie por detrás de lo ya emitido."""
    sql("DELETE FROM correlativo WHERE clave = :c", c=f"paciente:{ANIO}")
    mayor = sql(
        "SELECT COALESCE(MAX(split_part(codigo, '-', 3)::int), 0) FROM paciente "
        "WHERE codigo LIKE :p",
        p=f"PAC-{ANIO}-%",
    ).scalar_one()

    assert correlativos.codigo_expediente(db) == f"PAC-{ANIO}-{mayor + 1:04d}"


def test_el_orden_es_numerico_no_alfabetico(db, sql):
    """Con `max()` sobre texto, 'PAC-…-9999' ganaría siempre a 'PAC-…-10000'."""
    sql(
        "INSERT INTO paciente (codigo, nombres, apellidos) VALUES (:c, 'Serie', 'Larga')",
        c=f"PAC-{ANIO}-10000",
    )
    sql("DELETE FROM correlativo WHERE clave = :c", c=f"paciente:{ANIO}")

    assert correlativos.codigo_expediente(db) == f"PAC-{ANIO}-10001"


def test_los_recibos_del_seed_no_se_repiten(db, sql):
    ultimo = sql("SELECT MAX(numero_recibo) FROM pago").scalar_one()
    assert correlativos.numero_recibo(db) == ultimo + 1
