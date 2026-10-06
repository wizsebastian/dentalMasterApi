"""Regresión sobre la base: el esquema y los catálogos son la fundación del resto.

Estas aserciones son un subconjunto de db/99_verify.sql, ejecutadas desde pytest
para que un cambio en el modelo las rompa en CI. El reporte completo de las 98
aserciones sigue siendo `psql -f db/99_verify.sql`.
"""


def test_estructura_del_esquema(sql):
    tablas = sql(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema='public' AND table_type='BASE TABLE' "
        "AND table_name <> 'alembic_version'"
    ).scalar_one()
    vistas = sql(
        "SELECT count(*) FROM information_schema.views WHERE table_schema='public'"
    ).scalar_one()
    enums = sql(
        "SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace "
        "WHERE t.typtype='e' AND n.nspname='public'"
    ).scalar_one()

    assert tablas == 56
    assert vistas == 6
    assert enums == 13


def test_indice_unico_parcial_del_odontograma(sql):
    """Garantiza un solo odontograma vigente por paciente."""
    assert (
        sql(
            "SELECT count(*) FROM pg_indexes "
            "WHERE schemaname='public' AND indexname='uq_odontograma_actual'"
        ).scalar_one()
        == 1
    )


def test_plan_item_total_es_columna_generada(sql):
    assert (
        sql(
            "SELECT is_generated FROM information_schema.columns "
            "WHERE table_name='plan_item' AND column_name='total'"
        ).scalar_one()
        == "ALWAYS"
    )


def test_procedimiento_total_es_columna_generada(sql):
    """El cargo al paciente lo calcula la base: cantidad × precio − descuento."""
    assert (
        sql(
            "SELECT is_generated FROM information_schema.columns "
            "WHERE table_name='procedimiento' AND column_name='total'"
        ).scalar_one()
        == "ALWAYS"
    )


def test_todo_modelo_mapea_contra_el_esquema(db):
    """Un modelo con una columna que no existe sólo fallaría al consultarlo.

    Los modelos no generan el esquema, así que nada más los compara con él.
    """
    from sqlalchemy import select

    from app.models import Base

    for mapeo in Base.registry.mappers:
        db.execute(select(mapeo.class_).limit(1)).all()


def test_catalogo_dental_completo(sql):
    assert sql("SELECT count(*) FROM diente").scalar_one() == 52
    assert sql("SELECT count(*) FROM diente WHERE denticion='permanente'").scalar_one() == 32
    assert sql("SELECT count(*) FROM diente WHERE denticion='temporal'").scalar_one() == 20
    assert sql("SELECT count(*) FROM superficie").scalar_one() == 6
    assert sql("SELECT count(*) FROM condicion_dental").scalar_one() == 35


def test_todo_servicio_tiene_precio_particular(sql):
    huerfanos = sql(
        "SELECT count(*) FROM servicio s WHERE NOT EXISTS ("
        "  SELECT 1 FROM precio_servicio ps"
        "  WHERE ps.servicio_id = s.id AND ps.lista_precio_id = 1)"
    ).scalar_one()
    assert huerfanos == 0
