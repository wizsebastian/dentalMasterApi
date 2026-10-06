"""Cuentas de acceso: sólo administración, y con la misma política de contraseñas."""

RUTA = "/api/v1/usuarios"
LOGIN = "/api/v1/auth/login"

BUENA = "Molar-Azul-Lluvia-47"
NUEVO = {"email": "Caja@DentalSonrisa.do", "rol": "facturacion", "password": BUENA}


def test_solo_administracion_ve_las_cuentas(client, cabeceras_doctor, cabeceras_admin):
    assert client.get(RUTA, headers=cabeceras_doctor).status_code == 403

    cuentas = client.get(RUTA, headers=cabeceras_admin).json()
    assert len(cuentas) == 5
    assert all("password_hash" not in c for c in cuentas)


def test_alta_normaliza_el_email_y_permite_entrar(client, cabeceras_admin):
    r = client.post(RUTA, json=NUEVO, headers=cabeceras_admin)

    assert r.status_code == 201, r.text
    assert r.json()["email"] == "caja@dentalsonrisa.do"
    entrada = client.post(LOGIN, json={"email": "caja@dentalsonrisa.do", "password": BUENA})
    assert entrada.status_code == 200


def test_la_pantalla_no_salta_la_politica_de_contrasenas(client, cabeceras_admin):
    for mala in ("corta", "123456789012345", "dentaldentaldental"):
        r = client.post(RUTA, json={**NUEVO, "password": mala}, headers=cabeceras_admin)
        assert r.status_code == 422, mala
        assert r.json()["detail"].startswith("password:")


def test_email_repetido_es_conflicto(client, cabeceras_admin):
    r = client.post(
        RUTA, json={**NUEVO, "email": "recepcion@dentalsonrisa.do"}, headers=cabeceras_admin
    )
    assert r.status_code == 409


def test_un_usuario_desactivado_no_entra(client, cabeceras_admin):
    recepcion = next(
        c for c in client.get(RUTA, headers=cabeceras_admin).json() if c["rol"] == "recepcion"
    )
    client.patch(f"{RUTA}/{recepcion['id']}", json={"activo": False}, headers=cabeceras_admin)

    r = client.post(LOGIN, json={"email": recepcion["email"], "password": "dental2026"})
    assert r.status_code == 403


def test_administracion_no_puede_dejarse_fuera(client, cabeceras_admin):
    yo = client.get("/api/v1/auth/me", headers=cabeceras_admin).json()

    assert (
        client.patch(
            f"{RUTA}/{yo['id']}", json={"activo": False}, headers=cabeceras_admin
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"{RUTA}/{yo['id']}", json={"rol": "doctor"}, headers=cabeceras_admin
        ).status_code
        == 409
    )


def test_rotar_la_contrasena_de_otro(client, cabeceras_admin):
    recepcion = next(
        c for c in client.get(RUTA, headers=cabeceras_admin).json() if c["rol"] == "recepcion"
    )
    r = client.post(
        f"{RUTA}/{recepcion['id']}/password", json={"password": BUENA}, headers=cabeceras_admin
    )

    assert r.status_code == 204
    assert (
        client.post(LOGIN, json={"email": recepcion["email"], "password": BUENA}).status_code == 200
    )
    assert (
        client.post(LOGIN, json={"email": recepcion["email"], "password": "dental2026"}).status_code
        == 401
    )
