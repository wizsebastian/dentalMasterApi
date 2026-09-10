"""Ficha médica: es un PUT completo, no un PATCH campo a campo."""

RUTA = "/api/v1/pacientes/1/ficha"

MINIMA = {"motivo_consulta": "Revisión"}


def test_leer_la_ficha_del_seed(client, cabeceras_doctor):
    cuerpo = client.get(RUTA, headers=cabeceras_doctor).json()

    assert cuerpo["paciente_id"] == 1
    assert [c["codigo"] for c in cuerpo["condiciones"]] == ["DM"]
    assert [a["nombre"] for a in cuerpo["alergias"]] == ["Penicilina"]
    assert cuerpo["alergias"][0]["severidad"] == "severa"


def test_el_paciente_sin_ficha_devuelve_404_explicativo(client, cabeceras_doctor):
    """El paciente 2 del seed no tiene ficha... salvo que el seed diga lo contrario."""
    r = client.get("/api/v1/pacientes/99999/ficha", headers=cabeceras_doctor)
    assert r.status_code == 404


def test_guardar_reemplaza_las_colecciones_enteras(client, cabeceras_doctor):
    """Quitar una alergia es simplemente no enviarla."""
    antes = client.get(RUTA, headers=cabeceras_doctor).json()
    assert antes["alergias"], "el caso pierde sentido sin alergias previas"

    despues = client.put(
        RUTA,
        json={**MINIMA, "condiciones": [], "alergias": [], "medicamentos": []},
        headers=cabeceras_doctor,
    ).json()

    assert despues["alergias"] == []
    assert despues["condiciones"] == []


def test_guardar_conserva_los_datos_del_catalogo(client, cabeceras_doctor):
    """Al escribir sólo el id, la respuesta debe traer nombre, riesgo y alerta."""
    cuerpo = client.put(
        RUTA,
        json={
            **MINIMA,
            "condiciones": [{"condicion_medica_id": 1, "controlado": False}],
            "alergias": [{"alergia_id": 1, "severidad": "severa"}],
        },
        headers=cabeceras_doctor,
    ).json()

    condicion = cuerpo["condiciones"][0]
    assert condicion["nombre"] and condicion["riesgo"]
    assert condicion["controlado"] is False


def test_una_condicion_repetida_no_rompe_la_clave_compuesta(client, cabeceras_doctor):
    """`ficha_condicion` tiene PK (ficha, condición): el duplicado se descarta."""
    cuerpo = client.put(
        RUTA,
        json={
            **MINIMA,
            "condiciones": [
                {"condicion_medica_id": 1},
                {"condicion_medica_id": 1, "detalle": "repetida"},
            ],
        },
        headers=cabeceras_doctor,
    ).json()

    assert len(cuerpo["condiciones"]) == 1


def test_crear_la_ficha_de_un_paciente_que_no_la_tiene(client, cabeceras_doctor):
    nuevo = client.post(
        "/api/v1/pacientes",
        json={
            "nombres": "Sin",
            "apellidos": "Ficha",
            "fecha_nacimiento": "2000-05-05",
            "sexo": "O",
        },
        headers=cabeceras_doctor,
    ).json()

    assert (
        client.get(f"/api/v1/pacientes/{nuevo['id']}/ficha", headers=cabeceras_doctor).status_code
        == 404
    )

    creada = client.put(
        f"/api/v1/pacientes/{nuevo['id']}/ficha",
        json={"motivo_consulta": "Primera visita", "fuma": True, "cigarrillos_dia": 5},
        headers=cabeceras_doctor,
    )
    assert creada.status_code == 200
    assert creada.json()["cigarrillos_dia"] == 5


def test_los_medicamentos_admiten_repeticiones(client, cabeceras_doctor):
    """A diferencia de condiciones y alergias, `ficha_medicamento` tiene id propio."""
    cuerpo = client.put(
        RUTA,
        json={
            **MINIMA,
            "medicamentos": [
                {"nombre": "Ibuprofeno", "dosis": "400mg"},
                {"nombre": "Ibuprofeno", "dosis": "600mg"},
            ],
        },
        headers=cabeceras_doctor,
    ).json()

    assert len(cuerpo["medicamentos"]) == 2


def test_valores_fuera_de_rango_se_rechazan(client, cabeceras_doctor):
    r = client.put(RUTA, json={**MINIMA, "semanas_gestacion": 60}, headers=cabeceras_doctor)
    assert r.status_code == 422


def test_los_campos_criticos_para_cirugia_se_guardan(client, cabeceras_doctor):
    """anticoagulantes y bifosfonatos cambian el protocolo de implantes."""
    cuerpo = client.put(
        RUTA,
        json={**MINIMA, "anticoagulantes": True, "bifosfonatos": True},
        headers=cabeceras_doctor,
    ).json()

    assert cuerpo["anticoagulantes"] is True
    assert cuerpo["bifosfonatos"] is True
