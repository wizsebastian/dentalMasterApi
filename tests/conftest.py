import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

os.environ.setdefault("SECRET_KEY", "test-secret")

from app.db.session import SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def db():
    """Sesión aislada: todo lo que escriba un test se revierte al terminar.

    La sesión se ata a una conexión con una transacción externa abierta y
    `join_transaction_mode="create_savepoint"`, de modo que los `commit()` del
    código de producción liberan un savepoint en lugar de confirmar de verdad.
    Así los tests pueden ejercitar los endpoints tal cual, sin tocar los datos
    demo sobre los que se apoyan las 101 aserciones de db/99_verify.sql.
    """
    conexion = engine.connect()
    transaccion = conexion.begin()
    sesion = Session(bind=conexion, join_transaction_mode="create_savepoint")

    try:
        yield sesion
    finally:
        sesion.close()
        transaccion.rollback()
        conexion.close()


@pytest.fixture
def client(db) -> TestClient:
    """Cliente HTTP que comparte la sesión revertible del test."""
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def sql(db):
    def run(statement: str, **params):
        return db.execute(text(statement), params)

    return run


def _token(client: TestClient, email: str, password: str = "dental2026") -> str:
    respuesta = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["access_token"]


@pytest.fixture
def cabeceras_doctor(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(client, 'laura.fernandez@dentalsonrisa.do')}"}


@pytest.fixture
def cabeceras_admin(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(client, 'admin@dentalsonrisa.do')}"}


@pytest.fixture
def cabeceras_recepcion(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(client, 'recepcion@dentalsonrisa.do')}"}


@pytest.fixture
def sesion_limpia():
    """Sesión normal, sin reversión. Sólo para comprobaciones de solo lectura."""
    with SessionLocal() as sesion:
        yield sesion
