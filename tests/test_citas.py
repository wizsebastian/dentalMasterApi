"""Agenda: huecos, sobrecupo, reprogramación y estados."""

RUTA = "/api/v1/citas"

# Doctor 2 tiene la cita 4 el 18-sep-2026 de 11:00 a 12:00 (confirmada).
OCUPADO = "2026-09-18T11:30:00-04:00"
LIBRE = "2031-03-02T09:00:00-04:00"

NUEVA = {"paciente_id": 2, "doctor_id": 1, "inicio": LIBRE}


def _crear(client, cabeceras, **cambios):
    return client.post(RUTA, json={**NUEVA, **cambios}, headers=cabeceras)


def test_la_semana_trae_sus_citas_con_los_nombres(client, cabeceras_recepcion):
    r = client.get(
        f"{RUTA}?desde=2026-09-14T00:00:00-04:00&hasta=2026-09-21T00:00:00-04:00",
        headers=cabeceras_recepcion,
    )
    assert r.status_code == 200, r.text
    citas = r.json()
    assert [c["id"] for c in citas] == [4]
    assert citas[0]["paciente_nombre"] == "Juan Carlos Peña Rosario"
    assert citas[0]["doctor_nombre"] == "Miguel Antonio Reyes Peralta"


def test_sin_tramo_ni_paciente_no_hay_listado(client, cabeceras_recepcion):
    """La agenda entera no se pide nunca de una vez."""
    assert client.get(RUTA, headers=cabeceras_recepcion).status_code == 422
    r = client.get(
        f"{RUTA}?desde=2026-01-01T00:00:00-04:00&hasta=2026-12-31T00:00:00-04:00",
        headers=cabeceras_recepcion,
    )
    assert r.status_code == 422


def test_las_citas_de_un_paciente(client, cabeceras_doctor):
    citas = client.get(f"{RUTA}?paciente_id=1", headers=cabeceras_doctor).json()
    assert [c["id"] for c in citas] == [1, 2, 3, 4]


def test_la_duracion_sale_del_servicio(client, cabeceras_recepcion, sql):
    """REST-001 dura 40 minutos; sin servicio, 30."""
    resina = sql("SELECT id FROM servicio WHERE codigo = 'REST-001'").scalar_one()

    con_servicio = _crear(client, cabeceras_recepcion, servicio_id=resina).json()
    sin_servicio = _crear(client, cabeceras_recepcion, inicio="2031-03-03T09:00:00-04:00").json()
    a_medida = _crear(
        client, cabeceras_recepcion, inicio="2031-03-04T09:00:00-04:00", duracion_min=90
    ).json()

    assert con_servicio["fin"].startswith("2031-03-02T13:40") or "09:40" in con_servicio["fin"]
    assert con_servicio["servicio_nombre"] == "Resina · 1 superficie"
    assert _minutos(sin_servicio) == 30
    assert _minutos(a_medida) == 90


def _minutos(cita) -> int:
    from datetime import datetime

    inicio = datetime.fromisoformat(cita["inicio"])
    fin = datetime.fromisoformat(cita["fin"])
    return int((fin - inicio).total_seconds() // 60)


def test_un_doctor_no_esta_en_dos_citas_a_la_vez(client, cabeceras_recepcion):
    r = _crear(client, cabeceras_recepcion, doctor_id=2, inicio=OCUPADO)

    assert r.status_code == 409
    assert "Juan Carlos Peña Rosario" in r.json()["detail"]
    assert "sobrecupo" in r.json()["detail"]


def test_el_sobrecupo_solapa_a_proposito_y_exige_motivo(client, cabeceras_recepcion):
    sin_motivo = _crear(client, cabeceras_recepcion, doctor_id=2, inicio=OCUPADO, sobrecupo=True)
    assert sin_motivo.status_code == 422

    con_motivo = _crear(
        client,
        cabeceras_recepcion,
        doctor_id=2,
        inicio=OCUPADO,
        sobrecupo=True,
        sobrecupo_motivo="Urgencia: dolor agudo",
    )
    assert con_motivo.status_code == 201, con_motivo.text
    assert con_motivo.json()["sobrecupo"] is True


def test_un_sillon_no_se_ocupa_dos_veces(client, cabeceras_recepcion):
    """Doctores distintos, mismo sillón, mismo tramo."""
    primera = _crear(client, cabeceras_recepcion, unidad_id=1)
    segunda = _crear(client, cabeceras_recepcion, doctor_id=3, unidad_id=1)
    otro_sillon = _crear(client, cabeceras_recepcion, doctor_id=3, unidad_id=2)

    assert primera.status_code == 201, primera.text
    assert segunda.status_code == 409
    assert "Unidad 1" in segunda.json()["detail"]
    assert otro_sillon.status_code == 201


def test_una_cita_cancelada_libera_el_hueco(client, cabeceras_recepcion):
    cita = _crear(client, cabeceras_recepcion).json()
    client.post(
        f"{RUTA}/{cita['id']}/estado",
        json={"estado": "cancelada", "motivo": "El paciente avisó"},
        headers=cabeceras_recepcion,
    )

    otra = _crear(client, cabeceras_recepcion, paciente_id=3)
    assert otra.status_code == 201

    # Reabrir la cancelada volvería a ocupar un hueco que ya no está libre.
    reabrir = client.post(
        f"{RUTA}/{cita['id']}/estado", json={"estado": "agendada"}, headers=cabeceras_recepcion
    )
    assert reabrir.status_code == 409


def test_reprogramar_conserva_la_cita_y_deja_rastro(client, cabeceras_recepcion):
    cita = _crear(client, cabeceras_recepcion, duracion_min=45).json()
    client.post(f"{RUTA}/{cita['id']}/recordatorio", headers=cabeceras_recepcion)

    r = client.patch(
        f"{RUTA}/{cita['id']}",
        json={"inicio": "2031-03-05T15:00:00-04:00", "motivo_cambio": "Pidió la tarde"},
        headers=cabeceras_recepcion,
    )

    assert r.status_code == 200, r.text
    movida = r.json()
    assert movida["id"] == cita["id"]
    assert _minutos(movida) == 45, "al mover se conserva la duración"
    assert movida["recordatorio_enviado_en"] is None, "el recordatorio hablaba del horario viejo"

    detalle = client.get(f"{RUTA}/{cita['id']}", headers=cabeceras_recepcion).json()
    assert [e["tipo"] for e in detalle["eventos"]] == ["creada", "recordatorio", "reprogramada"]
    assert detalle["eventos"][-1]["motivo"] == "Pidió la tarde"


def test_reprogramar_sobre_un_hueco_ocupado_es_conflicto(client, cabeceras_recepcion):
    cita = _crear(client, cabeceras_recepcion, doctor_id=2).json()
    r = client.patch(f"{RUTA}/{cita['id']}", json={"inicio": OCUPADO}, headers=cabeceras_recepcion)
    assert r.status_code == 409


def test_el_recorrido_de_estados_de_una_visita(client, cabeceras_recepcion):
    cita = _crear(client, cabeceras_recepcion).json()
    ruta = f"{RUTA}/{cita['id']}/estado"

    for estado in ("confirmada", "en_sala", "atendida"):
        r = client.post(ruta, json={"estado": estado}, headers=cabeceras_recepcion)
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == estado

    # Atendida es final: ni se cancela ni se mueve.
    assert (
        client.post(ruta, json={"estado": "cancelada"}, headers=cabeceras_recepcion).status_code
        == 409
    )
    mover = client.patch(
        f"{RUTA}/{cita['id']}",
        json={"inicio": "2031-03-06T09:00:00-04:00"},
        headers=cabeceras_recepcion,
    )
    assert mover.status_code == 409


def test_no_asistio_no_es_lo_mismo_que_cancelada(client, cabeceras_recepcion):
    cita = _crear(client, cabeceras_recepcion).json()
    r = client.post(
        f"{RUTA}/{cita['id']}/estado", json={"estado": "no_asistio"}, headers=cabeceras_recepcion
    )
    assert r.json()["estado"] == "no_asistio"


def test_un_inicio_sin_zona_horaria_se_rechaza(client, cabeceras_recepcion):
    assert _crear(client, cabeceras_recepcion, inicio="2031-03-02T09:00:00").status_code == 422


def test_facturacion_no_agenda(client, cabeceras_admin, cabeceras_recepcion):
    """Facturación consulta la agenda pero no la mueve."""
    client.post(
        "/api/v1/usuarios",
        json={
            "email": "caja@dentalsonrisa.do",
            "rol": "facturacion",
            "password": "Molar-Azul-Lluvia-47",
        },
        headers=cabeceras_admin,
    )
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "caja@dentalsonrisa.do", "password": "Molar-Azul-Lluvia-47"},
    ).json()["access_token"]
    caja = {"Authorization": f"Bearer {token}"}

    assert client.get(f"{RUTA}?paciente_id=1", headers=caja).status_code == 200
    assert client.post(RUTA, json=NUEVA, headers=caja).status_code == 403


def test_la_clinica_para_membretes(client, cabeceras_recepcion):
    cuerpo = client.get("/api/v1/catalogos/clinica", headers=cabeceras_recepcion).json()
    assert cuerpo["nombre"] == "Clínica Dental Sonrisa"
    assert cuerpo["rnc"]
