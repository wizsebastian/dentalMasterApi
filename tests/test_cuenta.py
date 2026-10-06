"""La cuenta del paciente: pagos, aplicaciones, anulación, cuentas por cobrar y caja."""

from decimal import Decimal

CUENTA = "/api/v1/pacientes/{}/cuenta"
PAGOS = "/api/v1/pacientes/{}/pagos"


def _cuenta(client, cabeceras, paciente_id=1):
    return client.get(CUENTA.format(paciente_id), headers=cabeceras).json()


def _pagar(client, cabeceras, paciente_id=1, **datos):
    return client.post(
        PAGOS.format(paciente_id), json={"monto": "1000.00", **datos}, headers=cabeceras
    )


def test_el_estado_de_cuenta_del_seed(client, cabeceras_recepcion):
    """El paciente 1 debe 14 925: 8 925 de la consulta 2 y 6 000 de la 5."""
    cuenta = _cuenta(client, cabeceras_recepcion)

    assert (cuenta["cargos"], cuenta["pagado"], cuenta["balance"]) == (
        "61425.00",
        "46500.00",
        "14925.00",
    )
    assert [(p["consulta_id"], p["saldo"]) for p in cuenta["pendientes"]] == [
        (2, "8925.00"),
        (5, "6000.00"),
    ]
    assert len(cuenta["pagos"]) == 3


def test_un_pago_suelto_va_a_la_consulta_mas_antigua(client, cabeceras_recepcion):
    r = _pagar(client, cabeceras_recepcion, monto="10000.00", metodo="tarjeta")

    assert r.status_code == 201, r.text
    pago = r.json()
    # 8 925 cierran la consulta 2 y lo que queda empieza a cubrir la 5.
    assert {a["consulta_id"]: a["monto"] for a in pago["aplicaciones"]} == {
        2: "8925.00",
        5: "1075.00",
    }
    assert pago["sin_aplicar"] == "0.00" or Decimal(pago["sin_aplicar"]) == 0
    assert _cuenta(client, cabeceras_recepcion)["balance"] == "4925.00"


def test_cobrar_resto_dirige_el_pago_a_esa_consulta(client, cabeceras_recepcion):
    pago = _pagar(client, cabeceras_recepcion, monto="6000.00", consulta_id=5).json()

    assert [(a["consulta_id"], a["monto"]) for a in pago["aplicaciones"]] == [(5, "6000.00")]
    pendientes = _cuenta(client, cabeceras_recepcion)["pendientes"]
    assert [p["consulta_id"] for p in pendientes] == [2]


def test_lo_que_sobra_queda_como_credito_a_favor(client, cabeceras_recepcion):
    """El paciente 2 no debe nada: todo el pago es anticipo."""
    pago = _pagar(client, cabeceras_recepcion, paciente_id=2, monto="3000.00").json()

    assert pago["aplicaciones"] == []
    assert pago["sin_aplicar"] == "3000.00"
    cuenta = _cuenta(client, cabeceras_recepcion, 2)
    assert cuenta["balance"] == "-3000.00", "balance negativo = crédito a favor"
    assert cuenta["credito_sin_aplicar"] == "3000.00"


def test_el_anticipo_se_aplica_solo_a_la_consulta_nueva(
    client, cabeceras_recepcion, cabeceras_doctor, sql
):
    _pagar(client, cabeceras_recepcion, paciente_id=2, monto="3000.00")
    profilaxis = sql("SELECT id FROM servicio WHERE codigo = 'PREV-001'").scalar_one()

    consulta = client.post(
        "/api/v1/pacientes/2/consultas",
        json={"doctor_id": 1, "lineas": [{"servicio_id": profilaxis}]},
        headers=cabeceras_doctor,
    ).json()

    assert (consulta["total"], consulta["aplicado"], consulta["saldo"]) == (
        "2500.00",
        "2500.00",
        "0.00",
    )
    assert _cuenta(client, cabeceras_recepcion, 2)["credito_sin_aplicar"] == "500.00"


def test_los_recibos_son_correlativos(client, cabeceras_recepcion):
    primero = _pagar(client, cabeceras_recepcion).json()["numero_recibo"]
    segundo = _pagar(client, cabeceras_recepcion).json()["numero_recibo"]

    assert primero == 6, "el seed llega hasta el recibo 5"
    assert segundo == 7


def test_anular_conserva_el_recibo_y_devuelve_el_saldo(
    client, cabeceras_recepcion, cabeceras_admin
):
    pago = _pagar(client, cabeceras_recepcion, monto="8925.00", consulta_id=2).json()
    assert _cuenta(client, cabeceras_recepcion)["balance"] == "6000.00"

    r = client.post(
        f"/api/v1/pagos/{pago['id']}/anular",
        json={"motivo": "Se cobró dos veces"},
        headers=cabeceras_admin,
    )

    assert r.status_code == 200, r.text
    anulado = r.json()
    assert anulado["numero_recibo"] == pago["numero_recibo"]
    assert anulado["anulado_en"] is not None
    assert anulado["aplicaciones"] == []
    assert _cuenta(client, cabeceras_recepcion)["balance"] == "14925.00"

    # No se anula dos veces, ni se edita después.
    otra_vez = client.post(
        f"/api/v1/pagos/{pago['id']}/anular", json={"motivo": "Otra vez"}, headers=cabeceras_admin
    )
    assert otra_vez.status_code == 409


def test_recepcion_cobra_pero_no_anula(client, cabeceras_recepcion):
    pago = _pagar(client, cabeceras_recepcion).json()
    r = client.post(
        f"/api/v1/pagos/{pago['id']}/anular",
        json={"motivo": "Me equivoqué"},
        headers=cabeceras_recepcion,
    )
    assert r.status_code == 403


def test_un_pago_no_cambia_de_monto(client, cabeceras_recepcion):
    """Corregir el monto es anular y registrar otro: el PATCH ni siquiera lo acepta."""
    pago = _pagar(client, cabeceras_recepcion).json()

    r = client.patch(
        f"/api/v1/pagos/{pago['id']}", json={"monto": "5.00"}, headers=cabeceras_recepcion
    )
    assert r.status_code == 422

    ok = client.patch(
        f"/api/v1/pagos/{pago['id']}",
        json={"concepto": "Abono implante", "referencia": "AUTH-1"},
        headers=cabeceras_recepcion,
    )
    assert ok.json()["concepto"] == "Abono implante"
    assert ok.json()["monto"] == "1000.00"


def test_un_pago_no_se_dirige_a_la_consulta_de_otro(client, cabeceras_recepcion):
    """La consulta 2 es del paciente 1."""
    assert _pagar(client, cabeceras_recepcion, paciente_id=3, consulta_id=2).status_code == 422


def test_el_recibo_trae_al_paciente_y_el_balance(client, cabeceras_recepcion):
    pago = _pagar(client, cabeceras_recepcion, monto="925.00").json()
    recibo = client.get(f"/api/v1/pagos/{pago['id']}", headers=cabeceras_recepcion).json()

    assert recibo["paciente_nombre"] == "Juan Carlos Peña Rosario"
    assert recibo["balance_despues"] == "14000.00"
    assert recibo["recibido_por_email"] == "recepcion@dentalsonrisa.do"


def test_cuentas_por_cobrar(client, cabeceras_recepcion):
    cuerpo = client.get("/api/v1/cuentas-por-cobrar", headers=cabeceras_recepcion).json()

    assert cuerpo["pacientes"] == 1
    assert cuerpo["total"] == "14925.00"
    deudor = cuerpo["items"][0]
    assert (deudor["paciente_id"], deudor["consultas"]) == (1, 2)
    # La suma de los tramos de antigüedad es el total.
    assert sum(Decimal(t["balance"]) for t in cuerpo["antiguedad"]) == Decimal("14925.00")


def test_la_caja_del_dia_suma_por_metodo_y_deja_fuera_lo_anulado(
    client, cabeceras_recepcion, cabeceras_admin
):
    _pagar(client, cabeceras_recepcion, monto="1000.00", metodo="efectivo")
    _pagar(client, cabeceras_recepcion, monto="2500.00", metodo="tarjeta")
    malo = _pagar(client, cabeceras_recepcion, monto="700.00", metodo="efectivo").json()
    client.post(
        f"/api/v1/pagos/{malo['id']}/anular",
        json={"motivo": "Error de digitación"},
        headers=cabeceras_admin,
    )

    caja = client.get("/api/v1/caja", headers=cabeceras_recepcion).json()

    assert caja["total"] == "3500.00"
    assert caja["anulados"] == 1
    assert {m["metodo"]: m["monto"] for m in caja["por_metodo"]} == {
        "efectivo": "1000.00",
        "tarjeta": "2500.00",
    }
    assert len(caja["pagos"]) == 3, "el anulado se lista, pero no suma"


def test_los_saldos_concilian_despues_de_cobrar_y_anular(
    client, cabeceras_recepcion, cabeceras_admin, sql
):
    """La regla R-09 de la base, tras mover dinero desde la API."""
    _pagar(client, cabeceras_recepcion, monto="10000.00")
    anticipo = _pagar(client, cabeceras_recepcion, paciente_id=2, monto="800.00").json()
    client.post(
        f"/api/v1/pagos/{anticipo['id']}/anular",
        json={"motivo": "Devuelto"},
        headers=cabeceras_admin,
    )

    descuadrados = sql(
        "SELECT count(*) FROM v_estado_cuenta ec WHERE ec.balance <> COALESCE(("
        "  SELECT SUM(sc.saldo) FROM v_saldo_consulta sc WHERE sc.paciente_id = ec.paciente_id"
        "), 0) - ec.credito_sin_aplicar"
    ).scalar_one()
    assert descuadrados == 0
