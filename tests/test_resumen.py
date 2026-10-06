"""Resumen del paciente, seguros, tarifas nuevas y lo planificado en el odontograma."""

from decimal import Decimal

API = "/api/v1"


# --- Resumen -------------------------------------------------------------------


def test_resumen_sale_de_lo_registrado(client, cabeceras_recepcion):
    respuesta = client.get(f"{API}/pacientes/1/resumen", headers=cabeceras_recepcion)
    assert respuesta.status_code == 200, respuesta.text
    resumen = respuesta.json()

    assert Decimal(resumen["balance"]) == Decimal("14925.00")
    assert resumen["consultas"] == 4
    assert resumen["ultima_consulta"]["servicios"]
    assert resumen["seguro"]["aseguradora_nombre"] == "ARS Humano"
    assert [i["lote"] for i in resumen["implantes"]] == ["LT-2026-A4179"]

    plan = resumen["planes"][0]
    assert plan["codigo"] == "PT-2026-0001"
    assert plan["items"] == 6
    assert 0 < plan["hechos"] < plan["items"]
    assert plan["siguiente"]
    assert Decimal(plan["pendiente"]) > 0


def test_resumen_de_un_paciente_sin_historia(client, cabeceras_recepcion):
    nuevo = client.post(
        f"{API}/pacientes",
        headers=cabeceras_recepcion,
        json={"nombres": "Prueba", "apellidos": "Resumen", "celular": "8095550199"},
    ).json()
    resumen = client.get(f"{API}/pacientes/{nuevo['id']}/resumen", headers=cabeceras_recepcion)
    assert resumen.status_code == 200, resumen.text
    cuerpo = resumen.json()
    assert cuerpo["consultas"] == 0
    assert cuerpo["ultima_consulta"] is None
    assert cuerpo["planes"] == []
    assert Decimal(cuerpo["balance"]) == 0


# --- Seguros -------------------------------------------------------------------


def test_seguros_un_solo_principal(client, cabeceras_recepcion, sql):
    ars = sql("SELECT id FROM aseguradora WHERE codigo = 'ARS02'").scalar_one()
    creado = client.post(
        f"{API}/pacientes/1/seguros",
        headers=cabeceras_recepcion,
        json={"aseguradora_id": ars, "poliza": "UNI-1", "vigente_hasta": "2020-01-01"},
    )
    assert creado.status_code == 201, creado.text
    assert creado.json()["vigente"] is False

    seguros = client.get(f"{API}/pacientes/1/seguros", headers=cabeceras_recepcion).json()
    assert len(seguros) == 2
    assert [s["principal"] for s in seguros] == [True, False]
    assert seguros[0]["poliza"] == "UNI-1"

    assert (
        client.delete(
            f"{API}/seguros/{creado.json()['id']}", headers=cabeceras_recepcion
        ).status_code
        == 204
    )


def test_aseguradoras_no_incluye_particular(client, cabeceras_recepcion):
    nombres = [
        a["codigo"] for a in client.get(f"{API}/aseguradoras", headers=cabeceras_recepcion).json()
    ]
    assert "PARTIC" not in nombres
    assert "ARS01" in nombres


# --- Tarifas -------------------------------------------------------------------


def test_tarifa_nueva_copia_precios_con_ajuste_y_cobertura(client, cabeceras_admin, sql):
    ars = sql("SELECT id FROM aseguradora WHERE codigo = 'ARS02'").scalar_one()
    respuesta = client.post(
        f"{API}/listas-precio",
        headers=cabeceras_admin,
        json={"nombre": "ARS Universal 2026", "aseguradora_id": ars, "ajuste_pct": "-10",
              "cobertura_pct": "80"},
    )  # fmt: skip
    assert respuesta.status_code == 201, respuesta.text
    lista = respuesta.json()["id"]

    precios, particular = sql(
        "SELECT count(*), (SELECT count(*) FROM precio_servicio WHERE lista_precio_id = 1) "
        "FROM precio_servicio WHERE lista_precio_id = :l",
        l=lista,
    ).one()
    assert precios == particular
    precio, cobertura = sql(
        "SELECT p.precio, p.cobertura_pct FROM precio_servicio p "
        "JOIN servicio s ON s.id = p.servicio_id "
        "WHERE p.lista_precio_id = :l AND s.codigo = 'DX-001'",
        l=lista,
    ).one()
    assert precio == Decimal("1080.00")
    assert cobertura == Decimal("80.00")

    # Un plan cotizado con esa tarifa estima lo que cubre el seguro.
    plan = client.post(
        f"{API}/pacientes/1/planes",
        headers=cabeceras_admin,
        json={"doctor_id": 1, "lista_precio_id": lista},
    ).json()
    dx = sql("SELECT id FROM servicio WHERE codigo = 'DX-001'").scalar_one()
    con_item = client.post(
        f"{API}/planes/{plan['id']}/items", headers=cabeceras_admin, json={"servicio_id": dx}
    ).json()
    assert con_item["aseguradora_nombre"] == "ARS Universal"
    assert Decimal(con_item["total"]) == Decimal("1080.00")
    assert Decimal(con_item["cobertura_estimada"]) == Decimal("864.00")


def test_tarifa_repetida_y_solo_admin(client, cabeceras_admin, cabeceras_recepcion):
    cuerpo = {"nombre": "Convenio empresas"}
    assert (
        client.post(f"{API}/listas-precio", headers=cabeceras_recepcion, json=cuerpo).status_code
        == 403
    )
    assert (
        client.post(f"{API}/listas-precio", headers=cabeceras_admin, json=cuerpo).status_code == 201
    )
    assert (
        client.post(f"{API}/listas-precio", headers=cabeceras_admin, json=cuerpo).status_code == 409
    )


def test_la_tarifa_particular_no_se_desactiva(client, cabeceras_admin):
    respuesta = client.patch(
        f"{API}/listas-precio/1", headers=cabeceras_admin, json={"activo": False}
    )
    assert respuesta.status_code == 409


# --- Lo planificado en el odontograma --------------------------------------------


def _planificados(sql, paciente=2):
    return sql(
        "SELECT h.codigo_fdi, h.superficie, h.estado::text, h.plan_item_id "
        "FROM odontograma_hallazgo h JOIN odontograma o ON o.id = h.odontograma_id "
        "WHERE o.paciente_id = :p AND o.es_actual AND h.plan_item_id IS NOT NULL "
        "ORDER BY h.codigo_fdi, h.superficie",
        p=paciente,
    ).all()


def _plan_con_resina(client, cabeceras, sql, paciente=2):
    plan = client.post(
        f"{API}/pacientes/{paciente}/planes", headers=cabeceras, json={"doctor_id": 1}
    ).json()
    resina = sql("SELECT id FROM servicio WHERE codigo = 'REST-001'").scalar_one()
    plan = client.post(
        f"{API}/planes/{plan['id']}/items",
        headers=cabeceras,
        json={"servicio_id": resina, "codigo_fdi": 26, "superficies": "OD"},
    ).json()
    return plan, plan["items"][0], resina


def test_un_item_del_plan_pinta_planificado(client, cabeceras_doctor, sql):
    _, item, _ = _plan_con_resina(client, cabeceras_doctor, sql)
    assert _planificados(sql) == [
        (26, "D", "planificado", item["id"]),
        (26, "O", "planificado", item["id"]),
    ]


def test_editar_el_item_mueve_lo_pintado_y_quitarlo_lo_borra(client, cabeceras_doctor, sql):
    plan, item, _ = _plan_con_resina(client, cabeceras_doctor, sql)
    ruta = f"{API}/planes/{plan['id']}/items/{item['id']}"

    editado = client.patch(ruta, headers=cabeceras_doctor, json={"superficies": "M"})
    assert editado.status_code == 200, editado.text
    assert _planificados(sql) == [(26, "M", "planificado", item["id"])]

    assert client.delete(ruta, headers=cabeceras_doctor).status_code == 200
    assert _planificados(sql) == []


def test_ejecutar_el_item_lo_completa_y_quitar_la_linea_lo_devuelve(client, cabeceras_doctor, sql):
    plan, item, resina = _plan_con_resina(client, cabeceras_doctor, sql)
    consulta = client.post(
        f"{API}/pacientes/2/consultas",
        headers=cabeceras_doctor,
        json={
            "doctor_id": 1,
            "plan_id": plan["id"],
            "lineas": [
                {"servicio_id": resina, "codigo_fdi": 26, "superficies": "OD",
                 "plan_item_id": item["id"]}
            ],
        },
    )  # fmt: skip
    assert consulta.status_code == 201, consulta.text
    assert {fila[2] for fila in _planificados(sql)} == {"completado"}

    # Un ítem ejecutado sólo admite reordenarse.
    ruta = f"{API}/planes/{plan['id']}/items/{item['id']}"
    assert client.patch(ruta, headers=cabeceras_doctor, json={"cantidad": 2}).status_code == 409
    assert client.patch(ruta, headers=cabeceras_doctor, json={"fase": 2}).status_code == 200

    client.patch(
        f"{API}/consultas/{consulta.json()['id']}", headers=cabeceras_doctor, json={"lineas": []}
    )
    assert {fila[2] for fila in _planificados(sql)} == {"planificado"}


def test_rechazar_el_plan_retira_lo_propuesto(client, cabeceras_doctor, sql):
    plan, _, _ = _plan_con_resina(client, cabeceras_doctor, sql)
    ruta = f"{API}/planes/{plan['id']}"
    client.patch(ruta, headers=cabeceras_doctor, json={"estado": "presentado"})
    client.patch(ruta, headers=cabeceras_doctor, json={"estado": "rechazado"})
    assert _planificados(sql) == []

    client.patch(ruta, headers=cabeceras_doctor, json={"estado": "borrador"})
    assert len(_planificados(sql)) == 2


def test_lo_planificado_por_un_plan_viaja_a_la_version_nueva(client, cabeceras_doctor, sql):
    _, item, _ = _plan_con_resina(client, cabeceras_doctor, sql)
    nueva = client.post(f"{API}/pacientes/2/odontograma", headers=cabeceras_doctor, json={})
    assert nueva.status_code == 201, nueva.text
    assert [fila[3] for fila in _planificados(sql)] == [item["id"], item["id"]]
