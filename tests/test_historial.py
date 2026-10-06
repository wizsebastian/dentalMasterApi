"""Consultas con sus líneas, y planes de tratamiento."""

from datetime import UTC, datetime
from decimal import Decimal

HISTORIAL = "/api/v1/pacientes/{}/historial"
CONSULTAS = "/api/v1/pacientes/{}/consultas"
PLANES = "/api/v1/pacientes/{}/planes"

ANIO = datetime.now(UTC).year


def _servicio(sql, codigo: str) -> int:
    return sql("SELECT id FROM servicio WHERE codigo = :c", c=codigo).scalar_one()


def _hallazgos(sql, paciente_id: int, pieza: int):
    return sql(
        "SELECT h.superficie, cd.codigo, h.estado::text, h.procedimiento_id "
        "FROM odontograma_hallazgo h "
        "JOIN odontograma o ON o.id = h.odontograma_id AND o.es_actual "
        "JOIN condicion_dental cd ON cd.id = h.condicion_dental_id "
        "WHERE o.paciente_id = :p AND h.codigo_fdi = :f ORDER BY 1, 2",
        p=paciente_id,
        f=pieza,
    ).all()


# --- Lectura -------------------------------------------------------------------


def test_el_historial_agrupa_las_consultas_por_plan(client, cabeceras_doctor):
    cuerpo = client.get(HISTORIAL.format(1), headers=cabeceras_doctor).json()

    plan = cuerpo["planes"][0]
    assert plan["codigo"] == "PT-2026-0001"
    assert [c["id"] for c in plan["consultas"]] == [5, 2, 4], "lo más reciente primero"
    assert [c["id"] for c in cuerpo["sueltas"]] == [1], "la evaluación inicial no tiene plan"


def test_el_saldo_de_cada_consulta_viene_de_la_base(client, cabeceras_doctor):
    """Consulta 2: 48 925 de cargo, 40 000 aplicados, 8 925 de saldo."""
    plan = client.get(HISTORIAL.format(1), headers=cabeceras_doctor).json()["planes"][0]
    implante = next(c for c in plan["consultas"] if c["id"] == 2)

    assert (implante["total"], implante["aplicado"], implante["saldo"]) == (
        "48925.00",
        "40000.00",
        "8925.00",
    )


def test_el_plan_dice_cuanto_va_y_que_falta(client, cabeceras_doctor):
    plan = client.get("/api/v1/planes/1", headers=cabeceras_doctor).json()

    assert plan["cotizado"] == "109400.00"
    assert plan["total"] == "103930.00", "con el 5 % del plan"
    assert plan["ejecutado"] == "57725.00"
    hechos = {i["servicio_codigo"] for i in plan["items"] if i["ejecutado"]}
    assert hechos == {"REST-001", "IMPL-001"}


# --- Consultas -----------------------------------------------------------------


def test_una_consulta_suelta_toma_el_precio_de_la_tarifa(client, cabeceras_doctor, sql):
    r = client.post(
        CONSULTAS.format(2),
        json={
            "doctor_id": 1,
            "motivo": "Profilaxis",
            "lineas": [{"servicio_id": _servicio(sql, "PREV-001")}],
        },
        headers=cabeceras_doctor,
    )

    assert r.status_code == 201, r.text
    consulta = r.json()
    assert consulta["plan_id"] is None
    assert consulta["lineas"][0]["precio"] == "2500.00"
    assert (consulta["total"], consulta["aplicado"], consulta["saldo"]) == (
        "2500.00",
        "0",
        "2500.00",
    ) or consulta["saldo"] == "2500.00"


def test_cantidad_y_descuento_dan_el_total_de_la_linea(client, cabeceras_doctor, sql):
    consulta = client.post(
        CONSULTAS.format(2),
        json={
            "doctor_id": 1,
            "lineas": [
                {
                    "servicio_id": _servicio(sql, "DX-002"),
                    "codigo_fdi": 16,
                    "cantidad": 3,
                    "precio": "700.00",
                    "descuento_pct": "10",
                }
            ],
        },
        headers=cabeceras_doctor,
    ).json()

    assert consulta["lineas"][0]["total"] == "1890.00"
    assert Decimal(consulta["total"]) == Decimal("1890.00")


def test_una_linea_ejecutada_pinta_el_odontograma(client, cabeceras_doctor, sql):
    """Se pinta una vez: la resina en 26 MO deja dos caras restauradas, enlazadas a la línea."""
    assert _hallazgos(sql, 2, 26) == []

    consulta = client.post(
        CONSULTAS.format(2),
        json={
            "doctor_id": 1,
            "lineas": [
                {"servicio_id": _servicio(sql, "REST-002"), "codigo_fdi": 26, "superficies": "mo"}
            ],
        },
        headers=cabeceras_doctor,
    ).json()
    linea = consulta["lineas"][0]

    assert linea["superficies"] == "MO"
    assert _hallazgos(sql, 2, 26) == [
        ("M", "RES", "completado", linea["id"]),
        ("O", "RES", "completado", linea["id"]),
    ]


def test_lo_planificado_pasa_a_completado_en_vez_de_duplicarse(client, cabeceras_doctor, sql):
    antes = sql(
        "SELECT h.codigo_fdi, h.superficie, s.id, o.paciente_id "
        "FROM odontograma_hallazgo h "
        "JOIN odontograma o ON o.id = h.odontograma_id AND o.es_actual "
        "JOIN servicio s ON s.condicion_resultante_id = h.condicion_dental_id "
        "JOIN condicion_dental cd ON cd.id = h.condicion_dental_id AND cd.ambito = 'superficie' "
        "WHERE h.estado = 'planificado' AND h.superficie IS NOT NULL "
        "ORDER BY o.paciente_id, h.codigo_fdi, s.id LIMIT 1"
    ).one()
    pieza, cara, servicio_id, paciente_id = antes
    cuantos = len(_hallazgos(sql, paciente_id, pieza))

    r = client.post(
        CONSULTAS.format(paciente_id),
        json={
            "doctor_id": 1,
            "lineas": [{"servicio_id": servicio_id, "codigo_fdi": pieza, "superficies": cara}],
        },
        headers=cabeceras_doctor,
    )

    assert r.status_code == 201, r.text
    despues = _hallazgos(sql, paciente_id, pieza)
    assert len(despues) == cuantos, "no se añade una fila: la propuesta cambia de estado"
    assert any(h[0] == cara and h[2] == "completado" and h[3] is not None for h in despues)


def test_un_servicio_que_pide_pieza_no_se_registra_sin_ella(client, cabeceras_doctor, sql):
    r = client.post(
        CONSULTAS.format(2),
        json={"doctor_id": 1, "lineas": [{"servicio_id": _servicio(sql, "REST-001")}]},
        headers=cabeceras_doctor,
    )
    assert r.status_code == 422
    assert "línea 1" in r.json()["detail"]


def test_un_molar_no_tiene_cara_incisal(client, cabeceras_doctor, sql):
    r = client.post(
        CONSULTAS.format(2),
        json={
            "doctor_id": 1,
            "lineas": [
                {"servicio_id": _servicio(sql, "REST-001"), "codigo_fdi": 16, "superficies": "I"}
            ],
        },
        headers=cabeceras_doctor,
    )
    assert r.status_code == 422


def test_editar_las_lineas_reemplaza_y_redibuja(client, cabeceras_doctor, sql):
    resina = _servicio(sql, "REST-001")
    consulta = client.post(
        CONSULTAS.format(2),
        json={
            "doctor_id": 1,
            "lineas": [
                {"servicio_id": resina, "codigo_fdi": 26, "superficies": "O"},
                {"servicio_id": _servicio(sql, "PREV-001")},
            ],
        },
        headers=cabeceras_doctor,
    ).json()
    de_resina = next(x for x in consulta["lineas"] if x["codigo_fdi"] == 26)

    # Se quita la profilaxis y la resina pasa de la 26 a la 27.
    r = client.patch(
        f"/api/v1/consultas/{consulta['id']}",
        json={
            "lineas": [
                {"id": de_resina["id"], "servicio_id": resina, "codigo_fdi": 27, "superficies": "O"}
            ]
        },
        headers=cabeceras_doctor,
    )

    assert r.status_code == 200, r.text
    assert [x["codigo_fdi"] for x in r.json()["lineas"]] == [27]
    assert r.json()["total"] == "2800.00"
    assert _hallazgos(sql, 2, 26) == [], "lo que la línea pintó en la 26 se retira"
    assert [h[:3] for h in _hallazgos(sql, 2, 27)] == [("O", "RES", "completado")]


def test_una_consulta_cobrada_no_se_elimina(client, cabeceras_doctor):
    """La consulta 2 tiene 40 000 aplicados: es historia contable."""
    assert client.delete("/api/v1/consultas/2", headers=cabeceras_doctor).status_code == 409


def test_una_consulta_sin_cobros_se_elimina_con_lo_que_pinto(client, cabeceras_doctor, sql):
    consulta = client.post(
        CONSULTAS.format(2),
        json={
            "doctor_id": 1,
            "lineas": [
                {"servicio_id": _servicio(sql, "REST-001"), "codigo_fdi": 26, "superficies": "O"}
            ],
        },
        headers=cabeceras_doctor,
    ).json()

    assert (
        client.delete(f"/api/v1/consultas/{consulta['id']}", headers=cabeceras_doctor).status_code
        == 204
    )
    assert _hallazgos(sql, 2, 26) == []


def test_bajar_el_total_por_debajo_de_lo_cobrado_no_pierde_el_dinero(client, cabeceras_doctor, sql):
    """Consulta 4: una resina de 2 800 pagada entera. Si pasa a 1 000, sobran 1 800,
    que no se pierden: van a la siguiente consulta con saldo del paciente (la 2)."""
    linea = sql("SELECT id, servicio_id FROM procedimiento WHERE consulta_id = 4").one()

    r = client.patch(
        "/api/v1/consultas/4",
        json={
            "lineas": [
                {
                    "id": linea.id,
                    "servicio_id": linea.servicio_id,
                    "codigo_fdi": 16,
                    "superficies": "O",
                    "precio": "1000.00",
                    # Explícito: sin él se copiaría el 5 % del plan.
                    "descuento_pct": "0",
                    "plan_item_id": 1,
                }
            ]
        },
        headers=cabeceras_doctor,
    )

    assert r.status_code == 200, r.text
    assert (r.json()["total"], r.json()["aplicado"], r.json()["saldo"]) == (
        "1000.00",
        "1000.00",
        "0.00",
    )
    cuenta = sql(
        "SELECT credito_sin_aplicar, balance FROM v_estado_cuenta WHERE paciente_id = 1"
    ).one()
    assert cuenta.credito_sin_aplicar == Decimal("0.00")
    assert cuenta.balance == Decimal("13125.00"), "14 925 menos los 1 800 que bajó el cargo"
    saldo_implante = sql("SELECT saldo FROM v_saldo_consulta WHERE consulta_id = 2").scalar_one()
    assert saldo_implante == Decimal("7125.00"), "los 1 800 liberados cubren parte de la consulta 2"


def test_recepcion_lee_el_historial_pero_no_lo_escribe(client, cabeceras_recepcion):
    assert client.get(HISTORIAL.format(1), headers=cabeceras_recepcion).status_code == 200
    r = client.post(CONSULTAS.format(2), json={"doctor_id": 1}, headers=cabeceras_recepcion)
    assert r.status_code == 403


# --- Planes --------------------------------------------------------------------


def test_un_plan_nuevo_lleva_su_codigo_y_la_tarifa_particular(client, cabeceras_doctor):
    r = client.post(
        PLANES.format(2),
        json={"doctor_id": 1, "titulo": "Rehabilitación", "especialidad_id": 1},
        headers=cabeceras_doctor,
    )

    assert r.status_code == 201, r.text
    plan = r.json()
    assert plan["codigo"] == f"PT-{ANIO}-0002"
    assert plan["estado"] == "borrador"
    assert plan["lista_precio_id"] == 1
    assert plan["especialidad_nombre"] == "Odontología general"


def _plan_con_item(client, cabeceras, sql, **item):
    plan = client.post(
        PLANES.format(2), json={"doctor_id": 1, "descuento_pct": "10"}, headers=cabeceras
    ).json()
    r = client.post(
        f"/api/v1/planes/{plan['id']}/items",
        json={
            "servicio_id": _servicio(sql, "REST-001"),
            "codigo_fdi": 26,
            "superficies": "O",
            **item,
        },
        headers=cabeceras,
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_un_item_toma_el_precio_de_la_tarifa_del_plan(client, cabeceras_doctor, sql):
    plan = _plan_con_item(client, cabeceras_doctor, sql)

    assert plan["items"][0]["precio_unit"] == "2800.00"
    assert plan["cotizado"] == "2800.00"
    assert plan["total"] == "2520.00", "con el 10 % del plan"


def test_ejecutar_un_item_arranca_el_plan_y_copia_su_descuento(client, cabeceras_doctor, sql):
    plan = _plan_con_item(client, cabeceras_doctor, sql)
    item = plan["items"][0]

    consulta = client.post(
        CONSULTAS.format(2),
        json={
            "doctor_id": 1,
            "plan_id": plan["id"],
            "lineas": [
                {
                    "servicio_id": item["servicio_id"],
                    "codigo_fdi": 26,
                    "superficies": "O",
                    "plan_item_id": item["id"],
                }
            ],
        },
        headers=cabeceras_doctor,
    ).json()

    assert consulta["lineas"][0]["descuento_pct"] == "10.00"
    assert consulta["total"] == "2520.00"

    despues = client.get(f"/api/v1/planes/{plan['id']}", headers=cabeceras_doctor).json()
    assert despues["estado"] == "en_ejecucion"
    assert despues["items"][0]["ejecutado"] is True
    assert despues["ejecutado"] == "2520.00"

    # Lo ejecutado ya no se quita del plan.
    r = client.delete(f"/api/v1/planes/{plan['id']}/items/{item['id']}", headers=cabeceras_doctor)
    assert r.status_code == 409


def test_una_consulta_no_cuelga_del_plan_de_otro_paciente(client, cabeceras_doctor):
    """El plan 1 es del paciente 1."""
    r = client.post(
        CONSULTAS.format(2), json={"doctor_id": 1, "plan_id": 1}, headers=cabeceras_doctor
    )
    assert r.status_code == 422


def test_un_plan_finalizado_no_admite_consultas_hasta_reabrirlo(client, cabeceras_doctor):
    finalizar = client.patch(
        "/api/v1/planes/1", json={"estado": "finalizado"}, headers=cabeceras_doctor
    )
    assert finalizar.status_code == 200, finalizar.text
    assert finalizar.json()["cerrado_en"] is not None

    cerrada = client.post(
        CONSULTAS.format(1), json={"doctor_id": 1, "plan_id": 1}, headers=cabeceras_doctor
    )
    assert cerrada.status_code == 409

    client.patch("/api/v1/planes/1", json={"estado": "en_ejecucion"}, headers=cabeceras_doctor)
    reabierta = client.post(
        CONSULTAS.format(1), json={"doctor_id": 1, "plan_id": 1}, headers=cabeceras_doctor
    )
    assert reabierta.status_code == 201


def test_un_plan_con_consultas_no_se_elimina(client, cabeceras_doctor):
    assert client.delete("/api/v1/planes/1", headers=cabeceras_doctor).status_code == 409


def test_un_plan_no_salta_de_borrador_a_finalizado(client, cabeceras_doctor):
    plan = client.post(PLANES.format(2), json={"doctor_id": 1}, headers=cabeceras_doctor).json()
    r = client.patch(
        f"/api/v1/planes/{plan['id']}", json={"estado": "finalizado"}, headers=cabeceras_doctor
    )
    assert r.status_code == 409
