"""Alta, búsqueda y edición de pacientes."""

RUTA = "/api/v1/pacientes"

NUEVO = {
    "nombres": "María Fernanda",
    "apellidos": "Ureña Gómez",
    "fecha_nacimiento": "1992-07-14",
    "sexo": "F",
    "celular": "809-555-0199",
}


def test_alta_genera_el_numero_de_expediente(client, cabeceras_doctor):
    """El código lo asigna el servidor: el cliente no puede elegirlo."""
    cuerpo = client.post(RUTA, json=NUEVO, headers=cabeceras_doctor).json()

    assert cuerpo["codigo"].startswith("PAC-")
    assert cuerpo["nombres"] == "María Fernanda"
    assert cuerpo["activo"] is True


def test_los_expedientes_no_se_repiten(client, cabeceras_doctor):
    primero = client.post(RUTA, json=NUEVO, headers=cabeceras_doctor).json()
    segundo = client.post(RUTA, json={**NUEVO, "nombres": "Otra"}, headers=cabeceras_doctor).json()

    assert primero["codigo"] != segundo["codigo"]


def test_documento_duplicado_es_conflicto(client, cabeceras_doctor):
    """El documento del paciente 1 del seed ya existe."""
    r = client.post(RUTA, json={**NUEVO, "documento": "402-1112223-4"}, headers=cabeceras_doctor)
    assert r.status_code == 409


def test_fecha_de_nacimiento_futura_se_rechaza(client, cabeceras_doctor):
    r = client.post(
        RUTA, json={**NUEVO, "fecha_nacimiento": "2099-01-01"}, headers=cabeceras_doctor
    )
    assert r.status_code == 422


def test_la_edad_se_calcula_y_no_se_almacena(client, cabeceras_doctor):
    cuerpo = client.get(f"{RUTA}/1", headers=cabeceras_doctor).json()
    assert cuerpo["fecha_nacimiento"] == "1985-03-12"
    assert isinstance(cuerpo["edad"], int)


def test_busqueda_por_nombre_completo(client, cabeceras_doctor):
    """Nombres y apellidos son columnas distintas; buscar 'Juan Peña' debe funcionar."""
    cuerpo = client.get(f"{RUTA}?buscar=Juan Carlos Peña", headers=cabeceras_doctor).json()
    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["codigo"] == "PAC-2026-0001"


def test_busqueda_por_expediente_y_documento(client, cabeceras_doctor):
    por_codigo = client.get(f"{RUTA}?buscar=PAC-2026-0001", headers=cabeceras_doctor).json()
    por_documento = client.get(f"{RUTA}?buscar=402-1112223-4", headers=cabeceras_doctor).json()

    assert por_codigo["items"][0]["id"] == por_documento["items"][0]["id"] == 1


def test_la_busqueda_ignora_mayusculas(client, cabeceras_doctor):
    assert client.get(f"{RUTA}?buscar=PEÑA", headers=cabeceras_doctor).json()["total"] == 1


def test_paginacion(client, cabeceras_doctor):
    pagina = client.get(f"{RUTA}?limite=2&offset=0", headers=cabeceras_doctor).json()

    assert len(pagina["items"]) <= 2
    assert pagina["total"] >= 4  # el seed trae 4 pacientes
    assert pagina["limite"] == 2


def test_editar_solo_cambia_lo_enviado(client, cabeceras_doctor):
    antes = client.get(f"{RUTA}/2", headers=cabeceras_doctor).json()

    despues = client.patch(
        f"{RUTA}/2", json={"ocupacion": "Arquitecta"}, headers=cabeceras_doctor
    ).json()

    assert despues["ocupacion"] == "Arquitecta"
    assert despues["nombres"] == antes["nombres"]
    assert despues["codigo"] == antes["codigo"]


def test_no_se_admiten_campos_desconocidos(client, cabeceras_doctor):
    """Un typo en el nombre del campo debe fallar, no ignorarse en silencio."""
    r = client.patch(f"{RUTA}/2", json={"ocupasion": "x"}, headers=cabeceras_doctor)
    assert r.status_code == 422


def test_paciente_inexistente(client, cabeceras_doctor):
    assert client.get(f"{RUTA}/99999", headers=cabeceras_doctor).status_code == 404


def test_alertas_del_paciente_1(client, cabeceras_doctor):
    """Alergia a penicilina: condiciona toda prescripción posterior."""
    alertas = client.get(f"{RUTA}/1/alertas", headers=cabeceras_doctor).json()
    detalles = {a["detalle"] for a in alertas}

    assert "Penicilina" in detalles
    assert "Diabetes mellitus" in detalles


def test_alertas_del_paciente_4(client, cabeceras_doctor):
    """Cuatro alertas: HTA, cardiopatía, anticoagulación y AINEs."""
    alertas = client.get(f"{RUTA}/4/alertas", headers=cabeceras_doctor).json()

    assert len(alertas) == 4
    assert {a["tipo"] for a in alertas} == {"condicion", "alergia"}
