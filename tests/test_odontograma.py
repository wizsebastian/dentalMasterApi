"""Reglas del odontograma: versionado, inmutabilidad y validación de piezas.

Es lo que el esquema no puede garantizar por sí solo. El índice parcial
`uq_odontograma_actual` asegura una sola versión vigente, pero nada impide a
nivel de base escribir sobre una versión histórica ni registrar una cara oclusal
en un incisivo.
"""

import pytest

CAR = 2  # condicion_dental.codigo = 'CAR' (caries, ámbito superficie)
IMPL = 30  # 'IMPL' (implante, ámbito protésico → aplica a la pieza completa)

PACIENTE_CON_ODONTOGRAMA = 1


@pytest.fixture
def odontograma_id(client, cabeceras_doctor) -> int:
    r = client.get(
        f"/api/v1/pacientes/{PACIENTE_CON_ODONTOGRAMA}/odontograma", headers=cabeceras_doctor
    )
    assert r.status_code == 200
    return r.json()["id"]


def test_el_vigente_trae_el_color_del_catalogo(client, cabeceras_doctor):
    """El frontend pinta con `color_hex`; si no viaja, no puede dibujar."""
    cuerpo = client.get("/api/v1/pacientes/1/odontograma", headers=cabeceras_doctor).json()

    assert cuerpo["es_actual"] is True
    assert len(cuerpo["hallazgos"]) == 11

    caries = [h for h in cuerpo["hallazgos"] if h["condicion_codigo"] == "CAR"]
    assert caries and all(h["color_hex"] == "#E53935" for h in caries)


def test_la_pieza_36_tiene_ausencia_e_implante_planificado(client, cabeceras_doctor):
    """Caso real del seed: una pieza ausente con un implante propuesto encima."""
    cuerpo = client.get("/api/v1/pacientes/1/odontograma", headers=cabeceras_doctor).json()
    pieza_36 = {
        (h["condicion_codigo"], h["estado"]) for h in cuerpo["hallazgos"] if h["codigo_fdi"] == 36
    }

    assert ("AUS_EXT", "existente") in pieza_36
    assert ("IMPL", "planificado") in pieza_36


def test_superficie_nula_significa_toda_la_pieza(client, cabeceras_doctor):
    """No es un dato que falte: distingue hallazgo de pieza de hallazgo de cara."""
    cuerpo = client.get("/api/v1/pacientes/1/odontograma", headers=cabeceras_doctor).json()

    for hallazgo in cuerpo["hallazgos"]:
        if hallazgo["ambito"] == "superficie":
            assert hallazgo["superficie"] is not None
        else:
            assert hallazgo["superficie"] is None


def test_registrar_un_hallazgo_en_la_version_vigente(client, cabeceras_doctor, odontograma_id):
    r = client.post(
        f"/api/v1/odontogramas/{odontograma_id}/hallazgos",
        json={"codigo_fdi": 47, "superficie": "O", "condicion_dental_id": CAR},
        headers=cabeceras_doctor,
    )
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["condicion_codigo"] == "CAR"
    assert cuerpo["color_hex"] == "#E53935"
    assert cuerpo["estado"] == "existente"


def test_el_mismo_hallazgo_dos_veces_es_conflicto(client, cabeceras_doctor, odontograma_id):
    """El esquema tiene UNIQUE; se responde 409, no un error 500."""
    payload = {"codigo_fdi": 47, "superficie": "O", "condicion_dental_id": CAR}
    ruta = f"/api/v1/odontogramas/{odontograma_id}/hallazgos"

    assert client.post(ruta, json=payload, headers=cabeceras_doctor).status_code == 201
    assert client.post(ruta, json=payload, headers=cabeceras_doctor).status_code == 409


@pytest.mark.parametrize(
    ("codigo_fdi", "superficie", "condicion", "motivo"),
    [
        (46, "I", CAR, "un molar no tiene cara incisal"),
        (11, "O", CAR, "un incisivo no tiene cara oclusal"),
        (51, "O", CAR, "pieza temporal en odontograma permanente"),
        (99, "O", CAR, "la pieza no existe"),
        (46, "O", IMPL, "un implante es de pieza completa, no de cara"),
    ],
)
def test_hallazgos_incoherentes_se_rechazan(
    client, cabeceras_doctor, odontograma_id, codigo_fdi, superficie, condicion, motivo
):
    r = client.post(
        f"/api/v1/odontogramas/{odontograma_id}/hallazgos",
        json={"codigo_fdi": codigo_fdi, "superficie": superficie, "condicion_dental_id": condicion},
        headers=cabeceras_doctor,
    )
    assert r.status_code == 422, f"debería rechazarse: {motivo}"


def test_nueva_version_cierra_la_anterior(client, cabeceras_doctor, db):
    """Sólo puede haber un odontograma vigente por paciente."""
    from sqlalchemy import text

    r = client.post(
        "/api/v1/pacientes/1/odontograma",
        json={"denticion": "permanente", "copiar_hallazgos": True},
        headers=cabeceras_doctor,
    )
    assert r.status_code == 201
    nueva = r.json()
    assert nueva["version"] == 2
    assert nueva["es_actual"] is True

    vigentes = db.execute(
        text("SELECT count(*) FROM odontograma WHERE paciente_id = 1 AND es_actual")
    ).scalar_one()
    assert vigentes == 1


def test_la_version_nueva_hereda_lo_existente_pero_no_lo_planificado(client, cabeceras_doctor):
    """Lo planificado pertenece al plan que lo originó, no se arrastra solo."""
    previo = client.get("/api/v1/pacientes/1/odontograma", headers=cabeceras_doctor).json()
    heredables = [h for h in previo["hallazgos"] if h["estado"] in ("existente", "completado")]
    planificados = [h for h in previo["hallazgos"] if h["estado"] == "planificado"]
    assert planificados, "el caso pierde sentido si el seed no trae planificados"

    nueva = client.post(
        "/api/v1/pacientes/1/odontograma",
        json={"copiar_hallazgos": True},
        headers=cabeceras_doctor,
    ).json()

    assert len(nueva["hallazgos"]) == len(heredables)
    assert not [h for h in nueva["hallazgos"] if h["estado"] == "planificado"]


def test_sin_copiar_la_version_nueva_arranca_vacia(client, cabeceras_doctor):
    nueva = client.post(
        "/api/v1/pacientes/1/odontograma",
        json={"copiar_hallazgos": False},
        headers=cabeceras_doctor,
    ).json()
    assert nueva["hallazgos"] == []


def test_la_version_historica_no_admite_escritura(client, cabeceras_doctor, odontograma_id):
    """Un odontograma cerrado es un documento clínico: se consulta, no se corrige."""
    client.post("/api/v1/pacientes/1/odontograma", json={}, headers=cabeceras_doctor)

    r = client.post(
        f"/api/v1/odontogramas/{odontograma_id}/hallazgos",
        json={"codigo_fdi": 47, "superficie": "O", "condicion_dental_id": CAR},
        headers=cabeceras_doctor,
    )
    assert r.status_code == 409
    assert "histórico" in r.json()["detail"]


def test_la_version_historica_sigue_siendo_legible(client, cabeceras_doctor, odontograma_id):
    client.post("/api/v1/pacientes/1/odontograma", json={}, headers=cabeceras_doctor)

    r = client.get(f"/api/v1/odontogramas/{odontograma_id}", headers=cabeceras_doctor)
    assert r.status_code == 200
    assert r.json()["es_actual"] is False


def test_el_historial_lista_de_la_mas_reciente_a_la_mas_antigua(client, cabeceras_doctor):
    client.post("/api/v1/pacientes/1/odontograma", json={}, headers=cabeceras_doctor)

    versiones = client.get(
        "/api/v1/pacientes/1/odontograma/versiones", headers=cabeceras_doctor
    ).json()
    assert [v["version"] for v in versiones] == [2, 1]
    assert [v["es_actual"] for v in versiones] == [True, False]


def test_estado_de_la_pieza_se_registra_y_actualiza(client, cabeceras_doctor, odontograma_id):
    ruta = f"/api/v1/odontogramas/{odontograma_id}/dientes/47"
    payload = {
        "codigo_fdi": 47,
        "presente": True,
        "movilidad": 2,
        "sondaje_mm": "4.5",
        "sangrado": True,
    }

    creado = client.put(ruta, json=payload, headers=cabeceras_doctor)
    assert creado.status_code == 200
    assert creado.json()["movilidad"] == 2

    # El segundo PUT actualiza la misma fila, no crea otra (UNIQUE odontograma+pieza)
    actualizado = client.put(ruta, json={**payload, "movilidad": 1}, headers=cabeceras_doctor)
    assert actualizado.status_code == 200
    assert actualizado.json()["movilidad"] == 1


def test_borrar_un_hallazgo_mal_registrado(client, cabeceras_doctor, odontograma_id):
    creado = client.post(
        f"/api/v1/odontogramas/{odontograma_id}/hallazgos",
        json={"codigo_fdi": 47, "superficie": "O", "condicion_dental_id": CAR},
        headers=cabeceras_doctor,
    ).json()

    r = client.delete(
        f"/api/v1/odontogramas/{odontograma_id}/hallazgos/{creado['id']}", headers=cabeceras_doctor
    )
    assert r.status_code == 204

    restantes = client.get("/api/v1/pacientes/1/odontograma", headers=cabeceras_doctor).json()
    assert creado["id"] not in [h["id"] for h in restantes["hallazgos"]]
