"""Especialidades, unidades dentales y doctores."""

ESPECIALIDADES = "/api/v1/especialidades"
UNIDADES = "/api/v1/unidades"
DOCTORES = "/api/v1/doctores"

DOCTOR = {
    "documento": "001-9876543-2",
    "nombres": "Ana Lucía",
    "apellidos": "Mejía Santos",
    "licencia": "EXQ-20001",
    "email": "ana.mejia@dentalsonrisa.do",
    "porcentaje_comision": "35.00",
}


def test_las_especialidades_dicen_quien_las_usa(client, cabeceras_doctor):
    especialidades = client.get(ESPECIALIDADES, headers=cabeceras_doctor).json()

    assert len(especialidades) == 9
    assert sum(e["doctores"] for e in especialidades) == 7


def test_una_especialidad_con_doctores_no_se_borra(client, cabeceras_admin):
    con_doctores = next(
        e for e in client.get(ESPECIALIDADES, headers=cabeceras_admin).json() if e["doctores"]
    )
    r = client.delete(f"{ESPECIALIDADES}/{con_doctores['id']}", headers=cabeceras_admin)
    assert r.status_code == 409


def test_alta_y_baja_de_una_especialidad_sin_uso(client, cabeceras_admin):
    creada = client.post(ESPECIALIDADES, json={"nombre": "Operatoria"}, headers=cabeceras_admin)
    assert creada.status_code == 201, creada.text
    assert creada.json()["codigo"] == "OPERA"

    repetida = client.post(ESPECIALIDADES, json={"nombre": "operatoria"}, headers=cabeceras_admin)
    assert repetida.status_code == 409

    borrada = client.delete(f"{ESPECIALIDADES}/{creada.json()['id']}", headers=cabeceras_admin)
    assert borrada.status_code == 204


def test_una_especialidad_desactivada_sale_del_selector(client, cabeceras_admin):
    primera = client.get(ESPECIALIDADES, headers=cabeceras_admin).json()[0]
    client.patch(
        f"{ESPECIALIDADES}/{primera['id']}", json={"activo": False}, headers=cabeceras_admin
    )

    activas = client.get(ESPECIALIDADES, headers=cabeceras_admin).json()
    todas = client.get(f"{ESPECIALIDADES}?incluir_inactivas=true", headers=cabeceras_admin).json()
    assert primera["id"] not in {e["id"] for e in activas}
    assert primera["id"] in {e["id"] for e in todas}


# --- Unidades dentales ---------------------------------------------------------


def test_las_unidades_del_seed(client, cabeceras_recepcion):
    unidades = client.get(UNIDADES, headers=cabeceras_recepcion).json()
    assert [(u["nombre"], u["alquilada"]) for u in unidades] == [
        ("Unidad 1", False),
        ("Unidad 2", True),
    ]


def test_alta_de_unidad_en_la_sede_principal(client, cabeceras_admin):
    r = client.post(UNIDADES, json={"nombre": "Unidad 3", "orden": 3}, headers=cabeceras_admin)

    assert r.status_code == 201, r.text
    assert r.json()["sede_id"] == 1
    assert (
        client.post(UNIDADES, json={"nombre": "unidad 3"}, headers=cabeceras_admin).status_code
        == 409
    )


def test_solo_administracion_crea_unidades(client, cabeceras_recepcion):
    r = client.post(UNIDADES, json={"nombre": "Unidad 9"}, headers=cabeceras_recepcion)
    assert r.status_code == 403


def test_una_unidad_con_citas_no_se_borra(client, cabeceras_admin):
    """Las del seed tienen citas; una recién creada, no."""
    nueva = client.post(UNIDADES, json={"nombre": "Unidad de paso"}, headers=cabeceras_admin).json()

    assert client.delete(f"{UNIDADES}/1", headers=cabeceras_admin).status_code == 409
    assert client.delete(f"{UNIDADES}/{nueva['id']}", headers=cabeceras_admin).status_code == 204


# --- Doctores ------------------------------------------------------------------


def test_los_doctores_traen_su_especialidad_principal_primero(client, cabeceras_recepcion):
    doctores = client.get(DOCTORES, headers=cabeceras_recepcion).json()

    assert len(doctores) == 3
    for doctor in doctores:
        assert doctor["especialidades"][0]["principal"] is True
        assert not doctor["nombre_completo"].lower().startswith("dr")


def test_alta_de_doctor_con_especialidades(client, cabeceras_admin):
    r = client.post(DOCTORES, json={**DOCTOR, "especialidad_ids": [2, 1]}, headers=cabeceras_admin)

    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["nombre_completo"] == "Ana Lucía Mejía Santos"
    assert [(e["especialidad_id"], e["principal"]) for e in cuerpo["especialidades"]] == [
        (2, True),
        (1, False),
    ]


def test_documento_de_doctor_repetido_dice_cual_choca(client, cabeceras_admin):
    r = client.post(
        DOCTORES, json={**DOCTOR, "documento": "001-1234567-1"}, headers=cabeceras_admin
    )
    assert r.status_code == 409
    assert "documento" in r.json()["detail"]


def test_cambiar_las_especialidades_reemplaza_y_reordena(client, cabeceras_admin):
    r = client.patch(f"{DOCTORES}/1", json={"especialidad_ids": [5]}, headers=cabeceras_admin)

    assert r.status_code == 200, r.text
    assert [(e["especialidad_id"], e["principal"]) for e in r.json()["especialidades"]] == [
        (5, True)
    ]


def test_un_doctor_desactivado_sale_del_selector(client, cabeceras_admin):
    client.patch(f"{DOCTORES}/3", json={"activo": False}, headers=cabeceras_admin)
    assert 3 not in {d["id"] for d in client.get(DOCTORES, headers=cabeceras_admin).json()}
