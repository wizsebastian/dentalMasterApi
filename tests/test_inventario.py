"""Gastos, insumos con kárdex, receta de servicio e informes."""

from decimal import Decimal

SEPTIEMBRE = "desde=2026-09-01&hasta=2026-09-30"

GASTO = {
    "fecha": "2026-09-15",
    "monto": "3500.00",
    "categoria_id": 2,
    "descripcion": "Electricidad de septiembre",
    "metodo": "transferencia",
}


def _existencia(client, cabeceras, insumo_id):
    items = client.get("/api/v1/insumos", headers=cabeceras).json()["items"]
    return next(i for i in items if i["id"] == insumo_id)


# --- Gastos --------------------------------------------------------------------


def test_los_gastos_del_mes_por_tipo_y_categoria(client, cabeceras_admin):
    cuerpo = client.get(f"/api/v1/gastos?{SEPTIEMBRE}", headers=cabeceras_admin).json()

    assert cuerpo["total"] == "72650.00"
    assert {t["nombre"]: t["monto"] for t in cuerpo["por_tipo"]} == {
        "Consultorio": "52080.00",
        "Doctores": "20570.00",
    }
    assert cuerpo["por_categoria"][0]["nombre"] == "Alquiler", "de mayor a menor"
    assert len(cuerpo["items"]) == 3


def test_un_honorario_dice_de_que_doctor_es(client, cabeceras_admin):
    sin_doctor = client.post(
        "/api/v1/gastos",
        json={**GASTO, "tipo": "doctor", "categoria_id": 3},
        headers=cabeceras_admin,
    )
    assert sin_doctor.status_code == 422

    con_doctor = client.post(
        "/api/v1/gastos",
        json={**GASTO, "tipo": "doctor", "categoria_id": 3, "doctor_id": 1},
        headers=cabeceras_admin,
    )
    assert con_doctor.status_code == 201, con_doctor.text
    assert con_doctor.json()["doctor_nombre"] == "Laura Fernández Cruz"

    # Y lo que no es honorario no lleva doctor.
    de_mas = client.post("/api/v1/gastos", json={**GASTO, "doctor_id": 1}, headers=cabeceras_admin)
    assert de_mas.status_code == 422


def test_el_proveedor_es_catalogo_y_el_comprobante_no_se_repite(client, cabeceras_admin, sql):
    """El NCF B0100004512 del Depósito Dental ya está en el seed."""
    repetido = client.post(
        "/api/v1/gastos",
        json={**GASTO, "proveedor": "depósito dental del caribe", "ncf": "B0100004512"},
        headers=cabeceras_admin,
    )
    assert repetido.status_code == 409

    nuevo = client.post(
        "/api/v1/gastos",
        json={
            **GASTO,
            "proveedor": "Edesur",
            "proveedor_rnc": "1-01-82124-8",
            "ncf": "B0100009999",
        },
        headers=cabeceras_admin,
    )
    assert nuevo.status_code == 201, nuevo.text
    assert sql("SELECT count(*) FROM proveedor").scalar_one() == 2, "Edesur se dio de alta solo"


def test_un_ncf_mal_formado_se_rechaza(client, cabeceras_admin):
    r = client.post(
        "/api/v1/gastos",
        json={**GASTO, "proveedor": "Edesur", "ncf": "B01-123"},
        headers=cabeceras_admin,
    )
    assert r.status_code == 422


def test_la_compra_entra_al_kardex_y_anularla_la_saca(client, cabeceras_admin):
    antes = Decimal(_existencia(client, cabeceras_admin, 1)["existencia"])

    gasto = client.post(
        "/api/v1/gastos",
        json={
            **GASTO,
            "categoria_id": 4,
            "descripcion": "Resina",
            "compras": [{"insumo_id": 1, "cantidad": "5", "costo_unit": "2350.00"}],
        },
        headers=cabeceras_admin,
    ).json()

    resina = _existencia(client, cabeceras_admin, 1)
    assert Decimal(resina["existencia"]) == antes + 5
    assert resina["costo"] == "2350.00", "la compra actualiza el último costo"
    assert resina["bajo_minimo"] is False

    client.post(
        f"/api/v1/gastos/{gasto['id']}/anular",
        json={"motivo": "Se devolvió el pedido"},
        headers=cabeceras_admin,
    )
    assert Decimal(_existencia(client, cabeceras_admin, 1)["existencia"]) == antes


def test_recepcion_no_ve_los_gastos(client, cabeceras_recepcion):
    assert client.get("/api/v1/gastos", headers=cabeceras_recepcion).status_code == 403


# --- Insumos y kárdex ----------------------------------------------------------


def test_el_inventario_calcula_la_existencia_del_kardex(client, cabeceras_doctor):
    cuerpo = client.get("/api/v1/insumos", headers=cabeceras_doctor).json()

    assert cuerpo["insumos"] == 5
    assert cuerpo["bajo_minimo"] == 1
    resina = next(i for i in cuerpo["items"] if i["id"] == 1)
    assert (resina["existencia"], resina["bajo_minimo"]) == ("3.000", True), "3 con mínimo 3"
    laboratorio = next(i for i in cuerpo["items"] if i["id"] == 5)
    assert laboratorio["controla_stock"] is False
    # 3×2200 + 2×3200 + 106×45 + 6×550; el laboratorio no cuenta.
    assert cuerpo["valor"] == "21070.00"


def test_un_conteo_ajusta_por_la_diferencia(client, cabeceras_doctor):
    """En el estante hay 100 cartuchos; el sistema creía 106."""
    r = client.post(
        "/api/v1/insumos/3/movimientos",
        json={"motivo": "conteo", "cantidad": "100", "nota": "Conteo de octubre"},
        headers=cabeceras_doctor,
    )

    assert r.status_code == 201, r.text
    assert r.json()["existencia"] == "100.000"
    ultimo = client.get("/api/v1/insumos/3/movimientos", headers=cabeceras_doctor).json()[0]
    assert (ultimo["motivo"], ultimo["cantidad"]) == ("conteo", "-6.000")


def test_una_merma_sale_y_un_servicio_externo_no_tiene_kardex(client, cabeceras_doctor):
    r = client.post(
        "/api/v1/insumos/4/movimientos",
        json={"motivo": "merma", "cantidad": "1", "nota": "Caja mojada"},
        headers=cabeceras_doctor,
    )
    assert r.json()["existencia"] == "5.000"

    externo = client.post(
        "/api/v1/insumos/5/movimientos",
        json={"motivo": "compra", "cantidad": "1"},
        headers=cabeceras_doctor,
    )
    assert externo.status_code == 409


def test_alta_de_insumo_con_existencia_inicial(client, cabeceras_doctor):
    r = client.post(
        "/api/v1/insumos",
        json={
            "nombre": "Hilo retractor #00",
            "unidad": "carrete",
            "stock_minimo": "2",
            "costo": "950.00",
            "existencia_inicial": "4",
        },
        headers=cabeceras_doctor,
    )
    assert r.status_code == 201, r.text
    assert (r.json()["existencia"], r.json()["valor"]) == ("4.000", "3800.00000") or r.json()[
        "existencia"
    ] == "4.000"

    repetido = client.post(
        "/api/v1/insumos", json={"nombre": "hilo retractor #00"}, headers=cabeceras_doctor
    )
    assert repetido.status_code == 409, "un solo catálogo: sin duplicados"


# --- Receta y consumo ----------------------------------------------------------


def test_la_receta_da_el_costo_del_servicio(client, cabeceras_admin, sql):
    resina = sql("SELECT id FROM servicio WHERE codigo = 'REST-001'").scalar_one()
    receta = client.get(f"/api/v1/servicios/{resina}/insumos", headers=cabeceras_admin).json()

    assert len(receta) == 3
    assert sum(Decimal(r["costo"]) for r in receta) == Decimal("425.00")
    costos = client.get("/api/v1/costos-servicio", headers=cabeceras_admin).json()
    assert {c["servicio_id"]: c["costo_insumos"] for c in costos}[resina] == "425.00"


def test_ejecutar_un_servicio_descuenta_su_receta_y_quitarlo_la_devuelve(
    client, cabeceras_doctor, sql
):
    resina = sql("SELECT id FROM servicio WHERE codigo = 'REST-001'").scalar_one()
    cartuchos = Decimal(_existencia(client, cabeceras_doctor, 3)["existencia"])

    consulta = client.post(
        "/api/v1/pacientes/2/consultas",
        json={
            "doctor_id": 1,
            "lineas": [
                {"servicio_id": resina, "codigo_fdi": 26, "superficies": "O", "cantidad": 2}
            ],
        },
        headers=cabeceras_doctor,
    ).json()

    # Dos resinas: dos cartuchos de anestesia y dos décimas de jeringa.
    assert Decimal(_existencia(client, cabeceras_doctor, 3)["existencia"]) == cartuchos - 2
    assert _existencia(client, cabeceras_doctor, 1)["existencia"] == "2.800"

    client.delete(f"/api/v1/consultas/{consulta['id']}", headers=cabeceras_doctor)
    assert Decimal(_existencia(client, cabeceras_doctor, 3)["existencia"]) == cartuchos
    assert _existencia(client, cabeceras_doctor, 1)["existencia"] == "3.000"


def test_guardar_la_receta_la_reemplaza(client, cabeceras_admin, sql):
    profilaxis = sql("SELECT id FROM servicio WHERE codigo = 'PREV-001'").scalar_one()
    r = client.put(
        f"/api/v1/servicios/{profilaxis}/insumos",
        json=[{"insumo_id": 4, "cantidad": "0.02"}],
        headers=cabeceras_admin,
    )
    assert r.status_code == 200, r.text
    assert [(x["insumo_id"], x["costo"]) for x in r.json()] == [(4, "11.00")]


# --- Informes ------------------------------------------------------------------


def test_el_resumen_de_abril(client, cabeceras_admin):
    """Abril de 2026: el implante. Doctor 2 produjo 48 925 y se le cobraron 25 000."""
    cuerpo = client.get(
        "/api/v1/informes/resumen?desde=2026-04-01&hasta=2026-04-30", headers=cabeceras_admin
    ).json()

    assert cuerpo["ingresos"] == "25000.00"
    assert cuerpo["produccion"] == "48925.00"
    doctor = next(d for d in cuerpo["doctores"] if d["doctor_id"] == 2)
    assert (doctor["produccion"], doctor["cobrado"]) == ("48925.00", "25000.00")
    assert doctor["comision"] == "11250.00", "45 % de lo cobrado, no de lo producido"


def test_el_neto_es_ingresos_menos_gastos(client, cabeceras_admin):
    cuerpo = client.get(f"/api/v1/informes/resumen?{SEPTIEMBRE}", headers=cabeceras_admin).json()

    assert cuerpo["gastos"] == "72650.00"
    assert Decimal(cuerpo["neto"]) == Decimal(cuerpo["ingresos"]) - Decimal(cuerpo["gastos"])
    assert cuerpo["por_cobrar"] == "14925.00"
