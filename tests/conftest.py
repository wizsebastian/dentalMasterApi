import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

os.environ.setdefault("SECRET_KEY", "test-secret")

from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db():
    """Sesión que revierte al terminar: ningún test toca los datos demo."""
    session = SessionLocal()
    session.begin_nested()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def sql(db):
    def run(statement: str, **params):
        return db.execute(text(statement), params)

    return run
