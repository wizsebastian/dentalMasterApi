"""La guía de primeros pasos: el progreso sale de los datos, no de casillas."""

import pytest

API = "/api/v1"
CLAVE_BUENA = "Sonrisa-Prueba-7392"


@pytest.fixture
def clinica_nueva(sql):
    """La base tal como se entrega: sin doctores, unidades, equipo ni NCF, y con el
    nombre de fábrica. Todo dentro de la transacción de la prueba, que se revierte."""
    sql("UPDATE doctor SET activo = FALSE")
    sql("UPDATE unidad_dental SET activo = FALSE")
    sql("UPDATE secuencia_ncf SET activo = FALSE")
    sql("UPDATE usuario SET activo = FALSE WHERE rol <> 'admin'")
    sql(
        "UPDATE sede SET nombre = 'Mi clínica', telefono = NULL, "
        "onboarding_cerrado_en = NULL, catalogo_revisado_en = NULL"
    )


def _pasos(client, cabeceras):
    cuerpo = client.get(f"{API}/onboarding", headers=cabeceras).json()
    return {p["id"]: p["hecho"] for p in cuerpo["pasos"]}, cuerpo


def test_la_demo_no_arranca_con_la_guia(client, cabeceras_admin):
    cuerpo = client.get(f"{API}/onboarding", headers=cabeceras_admin).json()
    assert cuerpo["cerrado"] is True
    assert cuerpo["listo"] is True
    assert cuerpo["total"] == 6


def test_una_clinica_recien_entregada_va_en_cero(client, cabeceras_admin, clinica_nueva):
    pasos, cuerpo = _pasos(client, cabeceras_admin)
    assert not any(pasos.values())
    assert (cuerpo["hechos"], cuerpo["total"]) == (0, 6)
    assert cuerpo["listo"] is False
    assert cuerpo["cerrado"] is False
    # Dos son obligatorios: la clínica y los doctores.
    assert [p["id"] for p in cuerpo["pasos"] if p["obligatorio"]] == ["clinica", "doctores"]


def test_cada_alta_marca_su_paso(client, cabeceras_admin, clinica_nueva):
    # 1 · los datos de la clínica: el nombre de fábrica no cuenta, ni sin teléfono.
    client.patch(f"{API}/catalogos/clinica", headers=cabeceras_admin, json={"nombre": "Sonrisa"})
    assert _pasos(client, cabeceras_admin)[0]["clinica"] is False
    client.patch(
        f"{API}/catalogos/clinica", headers=cabeceras_admin, json={"telefono": "8095550100"}
    )
    assert _pasos(client, cabeceras_admin)[0]["clinica"] is True

    # 2 · un doctor
    doctor = client.post(
        f"{API}/doctores",
        headers=cabeceras_admin,
        json={"documento": "001-9999999-9", "nombres": "Ana", "apellidos": "Prueba"},
    )
    assert doctor.status_code == 201, doctor.text
    pasos, cuerpo = _pasos(client, cabeceras_admin)
    assert pasos["doctores"] is True
    assert cuerpo["listo"] is True, "con la clínica y un doctor ya se puede trabajar"

    # 3 · una unidad
    unidad = client.post(f"{API}/unidades", headers=cabeceras_admin, json={"nombre": "Sillón A"})
    assert unidad.status_code == 201, unidad.text
    assert _pasos(client, cabeceras_admin)[0]["unidades"] is True

    # 4 · un usuario que no es el administrador
    usuario = client.post(
        f"{API}/usuarios",
        headers=cabeceras_admin,
        json={"email": "nuevo@clinica.do", "rol": "recepcion", "password": CLAVE_BUENA},
    )
    assert usuario.status_code == 201, usuario.text
    assert _pasos(client, cabeceras_admin)[0]["equipo"] is True

    # 5 · una secuencia de NCF activa
    secuencia = client.post(
        f"{API}/secuencias-ncf",
        headers=cabeceras_admin,
        # La demo ya emitió los primeros B02: el rango nuevo tiene que empezar después.
        json={"tipo": "B02", "desde": 9001, "hasta": 9010},
    )
    assert secuencia.status_code == 201, secuencia.text
    assert _pasos(client, cabeceras_admin)[0]["ncf"] is True

    # 6 · el catálogo, que no deja rastro: se marca
    assert _pasos(client, cabeceras_admin)[0]["catalogo"] is False
    revisado = client.post(f"{API}/onboarding/revisar-catalogo", headers=cabeceras_admin)
    assert revisado.status_code == 200
    pasos, cuerpo = _pasos(client, cabeceras_admin)
    assert all(pasos.values())
    assert (cuerpo["hechos"], cuerpo["total"]) == (6, 6)


def test_un_usuario_desactivado_no_cuenta_como_equipo(client, cabeceras_admin, clinica_nueva):
    assert _pasos(client, cabeceras_admin)[0]["equipo"] is False


def test_no_se_puede_omitir_lo_obligatorio(client, cabeceras_admin, clinica_nueva):
    sin = client.post(f"{API}/onboarding/cerrar", headers=cabeceras_admin)
    assert sin.status_code == 409
    assert "obligatorios" in sin.json()["detail"]
    assert client.get(f"{API}/onboarding", headers=cabeceras_admin).json()["cerrado"] is False

    # Un `forzar` ya no existe: mandarlo no abre ninguna puerta.
    forzado = client.post(
        f"{API}/onboarding/cerrar", headers=cabeceras_admin, json={"forzar": True}
    )
    assert forzado.status_code == 409


def test_cerrar_con_lo_obligatorio(client, cabeceras_admin, clinica_nueva):
    client.patch(
        f"{API}/catalogos/clinica",
        headers=cabeceras_admin,
        json={"nombre": "Sonrisa", "telefono": "8095550100"},
    )
    client.post(
        f"{API}/doctores",
        headers=cabeceras_admin,
        json={"documento": "001-8888888-8", "nombres": "Ana", "apellidos": "Prueba"},
    )
    cerrada = client.post(f"{API}/onboarding/cerrar", headers=cabeceras_admin)
    assert cerrada.status_code == 200, cerrada.text
    assert cerrada.json()["cerrado"] is True


def test_el_resto_de_roles_sabe_si_esta_lista_pero_no_ve_el_detalle(client, cabeceras_recepcion):
    cuerpo = client.get(f"{API}/onboarding", headers=cabeceras_recepcion).json()
    assert cuerpo["listo"] is True
    assert cuerpo["cerrado"] is True
    assert cuerpo["pasos"] == []
    assert cuerpo["total"] == 0


def test_solo_administracion_escribe(client, cabeceras_recepcion, cabeceras_doctor):
    for cabeceras in (cabeceras_recepcion, cabeceras_doctor):
        revisar = client.post(f"{API}/onboarding/revisar-catalogo", headers=cabeceras)
        cerrar = client.post(f"{API}/onboarding/cerrar", headers=cabeceras)
        assert (revisar.status_code, cerrar.status_code) == (403, 403)


def test_exige_sesion(client):
    assert client.get(f"{API}/onboarding").status_code == 401
