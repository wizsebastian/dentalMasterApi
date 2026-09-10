"""Autenticación y control de acceso por rol."""

import pytest

LOGIN = "/api/v1/auth/login"


def test_login_correcto_devuelve_ambos_tokens(client):
    r = client.post(
        LOGIN, json={"email": "laura.fernandez@dentalsonrisa.do", "password": "dental2026"}
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["access_token"] and cuerpo["refresh_token"]


def test_password_incorrecta_y_email_inexistente_son_indistinguibles(client):
    """Distinguirlos permitiría enumerar qué cuentas existen."""
    mala = client.post(LOGIN, json={"email": "laura.fernandez@dentalsonrisa.do", "password": "x"})
    inexistente = client.post(LOGIN, json={"email": "nadie@ejemplo.do", "password": "x"})

    assert mala.status_code == inexistente.status_code == 401
    assert mala.json()["detail"] == inexistente.json()["detail"]


def test_sin_token_no_se_accede(client):
    assert client.get("/api/v1/pacientes").status_code == 401


def test_token_manipulado_se_rechaza(client, cabeceras_doctor):
    falso = cabeceras_doctor["Authorization"][:-4] + "AAAA"
    assert client.get("/api/v1/auth/me", headers={"Authorization": falso}).status_code == 401


def test_el_access_token_no_sirve_como_refresh(client):
    """Los tokens llevan `type`: usar uno donde va el otro no debe funcionar."""
    access = client.post(
        LOGIN, json={"email": "laura.fernandez@dentalsonrisa.do", "password": "dental2026"}
    ).json()["access_token"]

    assert client.post("/api/v1/auth/refresh", json={"refresh_token": access}).status_code == 401


def test_me_devuelve_el_doctor_asociado(client, cabeceras_doctor):
    cuerpo = client.get("/api/v1/auth/me", headers=cabeceras_doctor).json()
    assert cuerpo["rol"] == "doctor"
    assert cuerpo["doctor_nombre"] == "Laura Fernández Cruz"


def test_recepcion_no_escribe_en_la_historia_clinica(client, cabeceras_recepcion):
    """La ficha médica la escribe quien atiende, no recepción."""
    r = client.put("/api/v1/pacientes/1/ficha", json={}, headers=cabeceras_recepcion)
    assert r.status_code == 403


def test_recepcion_si_puede_dar_de_alta_pacientes(client, cabeceras_recepcion):
    r = client.post(
        "/api/v1/pacientes",
        json={
            "nombres": "Prueba",
            "apellidos": "Recepción",
            "fecha_nacimiento": "1990-01-01",
            "sexo": "F",
        },
        headers=cabeceras_recepcion,
    )
    assert r.status_code == 201


class TestFortalezaPassword:
    """La longitud sola no basta: '12345678912345' tiene catorce caracteres."""

    @pytest.mark.parametrize(
        "password",
        [
            "12345678912345",  # secuencia de dígitos
            "abcdefghijklm",  # secuencia de letras
            "aaaaaaaaaaaaaa",  # apenas un carácter distinto
            "corta1!",  # demasiado corta
            "qwertyuiop12",  # patrón de teclado
            "dental2026aa",  # nombre del producto
            "99887766554433",  # sólo dígitos
        ],
    )
    def test_rechaza_las_previsibles(self, password):
        from app.cli import revisar_password

        assert revisar_password(password) is not None

    @pytest.mark.parametrize("password", ["Roble-Cauce-91x", "mQ7v!raiz-lento"])
    def test_acepta_las_razonables(self, password):
        from app.cli import revisar_password

        assert revisar_password(password) is None
