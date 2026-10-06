"""Implantes: registro desde la línea de consulta, seguimiento y trazabilidad por lote."""

API = "/api/v1"


def _servicio_implante(sql) -> int:
    return sql("SELECT id FROM servicio WHERE codigo = 'IMPL-001'").scalar_one()


def _sistema(sql) -> int:
    return sql("SELECT id FROM sistema_implante ORDER BY id LIMIT 1").scalar_one()


def _consulta_con_implante(client, cabeceras, sql, pieza=46) -> dict:
    respuesta = client.post(
        f"{API}/pacientes/2/consultas",
        headers=cabeceras,
        json={
            "doctor_id": 2,
            "lineas": [{"servicio_id": _servicio_implante(sql), "codigo_fdi": pieza}],
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def test_la_linea_dice_si_es_implante_y_si_ya_tiene_lote(client, cabeceras_doctor, sql):
    linea = _consulta_con_implante(client, cabeceras_doctor, sql)["lineas"][0]
    assert linea["es_implante"] is True
    assert linea["implante_id"] is None


def test_registrar_desde_la_linea_hereda_pieza_doctor_y_fecha(client, cabeceras_doctor, sql):
    consulta = _consulta_con_implante(client, cabeceras_doctor, sql)
    linea = consulta["lineas"][0]

    respuesta = client.post(
        f"{API}/pacientes/2/implantes",
        headers=cabeceras_doctor,
        json={
            "sistema_implante_id": _sistema(sql),
            "procedimiento_id": linea["id"],
            "lote": " lt-2026-b0001 ",
            "diametro_mm": "4.1",
            "longitud_mm": "10",
            "torque_ncm": 35,
            "isq": 70,
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    implante = respuesta.json()

    assert implante["codigo_fdi"] == 46
    assert implante["doctor_id"] == 2
    assert implante["lote"] == "LT-2026-B0001"
    assert implante["estado"] == "colocado"
    assert implante["fecha_colocacion"] is not None
    # La colocación queda como primer hito del seguimiento.
    assert [e["tipo"] for e in implante["eventos"]] == ["colocacion"]

    releida = client.get(f"{API}/consultas/{consulta['id']}", headers=cabeceras_doctor).json()
    assert releida["lineas"][0]["implante_id"] == implante["id"]


def test_el_lote_es_obligatorio(client, cabeceras_doctor, sql):
    respuesta = client.post(
        f"{API}/pacientes/2/implantes",
        headers=cabeceras_doctor,
        json={"sistema_implante_id": _sistema(sql), "codigo_fdi": 46, "doctor_id": 2, "lote": " "},
    )
    assert respuesta.status_code == 422


def test_la_linea_debe_ser_de_un_servicio_de_implante(client, cabeceras_doctor, sql):
    # El procedimiento 1 del seed es una consulta de evaluación.
    respuesta = client.post(
        f"{API}/pacientes/1/implantes",
        headers=cabeceras_doctor,
        json={"sistema_implante_id": _sistema(sql), "procedimiento_id": 1, "lote": "X1"},
    )
    assert respuesta.status_code == 422
    assert "no es un servicio de implante" in respuesta.json()["detail"]


def test_linea_de_otro_paciente(client, cabeceras_doctor, sql):
    respuesta = client.post(
        f"{API}/pacientes/2/implantes",
        headers=cabeceras_doctor,
        json={"sistema_implante_id": _sistema(sql), "procedimiento_id": 5, "lote": "X1"},
    )
    assert respuesta.status_code == 422


def test_una_linea_con_implante_no_se_quita_de_la_consulta(client, cabeceras_doctor, sql):
    consulta = _consulta_con_implante(client, cabeceras_doctor, sql)
    client.post(
        f"{API}/pacientes/2/implantes",
        headers=cabeceras_doctor,
        json={
            "sistema_implante_id": _sistema(sql),
            "procedimiento_id": consulta["lineas"][0]["id"],
            "lote": "LT-9",
        },
    )
    respuesta = client.patch(
        f"{API}/consultas/{consulta['id']}", headers=cabeceras_doctor, json={"lineas": []}
    )
    assert respuesta.status_code == 409


def test_el_evento_de_carga_mueve_el_estado(client, cabeceras_doctor):
    respuesta = client.post(
        f"{API}/implantes/1/eventos",
        headers=cabeceras_doctor,
        json={"tipo": "carga", "fecha": "2026-09-20", "isq": 80, "hallazgos": "Corona atornillada"},
    )
    assert respuesta.status_code == 201, respuesta.text
    implante = respuesta.json()
    assert implante["estado"] == "cargado"
    assert implante["fecha_carga"] == "2026-09-20"
    assert implante["isq"] == 80
    assert len(implante["eventos"]) == 5


def test_un_control_no_cambia_el_estado(client, cabeceras_doctor):
    implante = client.post(
        f"{API}/implantes/1/eventos", headers=cabeceras_doctor, json={"tipo": "control"}
    ).json()
    assert implante["estado"] == "oseointegrado"


def test_buscar_por_lote_dice_a_quien_llamar(client, cabeceras_doctor):
    respuesta = client.get(f"{API}/implantes?lote=a4179", headers=cabeceras_doctor)
    assert respuesta.status_code == 200
    encontrados = respuesta.json()
    assert len(encontrados) == 1
    assert encontrados[0]["lote"] == "LT-2026-A4179"
    assert encontrados[0]["paciente_codigo"] == "PAC-2026-0001"
    assert encontrados[0]["paciente_telefono"]


def test_recepcion_no_busca_por_lote_ni_registra(client, cabeceras_recepcion, sql):
    assert client.get(f"{API}/implantes?lote=LT", headers=cabeceras_recepcion).status_code == 403
    respuesta = client.post(
        f"{API}/pacientes/1/implantes",
        headers=cabeceras_recepcion,
        json={"sistema_implante_id": _sistema(sql), "codigo_fdi": 36, "doctor_id": 2, "lote": "X"},
    )
    assert respuesta.status_code == 403


def test_editar_no_deja_el_lote_vacio(client, cabeceras_doctor):
    assert (
        client.patch(
            f"{API}/implantes/1", headers=cabeceras_doctor, json={"lote": None}
        ).status_code
        == 422
    )
    editado = client.patch(
        f"{API}/implantes/1", headers=cabeceras_doctor, json={"garantia_hasta": "2040-01-01"}
    )
    assert editado.status_code == 200
    assert editado.json()["lote"] == "LT-2026-A4179"


def test_sistemas(client, cabeceras_doctor):
    creado = client.post(
        f"{API}/sistemas-implante",
        headers=cabeceras_doctor,
        json={"marca": "Osstem", "linea": "TS III", "conexion": "Hexágono interno"},
    )
    assert creado.status_code == 201, creado.text
    nombres = [
        f"{s['marca']} {s['linea']}"
        for s in client.get(f"{API}/sistemas-implante", headers=cabeceras_doctor).json()
    ]
    assert "Osstem TS III" in nombres
