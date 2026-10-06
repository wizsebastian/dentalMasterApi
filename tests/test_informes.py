"""Reporte de un doctor: producción, cobros, comisión y quién puede verlo."""

from decimal import Decimal

API = "/api/v1"
ABRIL = "desde=2026-04-01&hasta=2026-04-30"


def _reporte(client, cabeceras, doctor=2, tramo=ABRIL):
    return client.get(f"{API}/informes/doctores/{doctor}?{tramo}", headers=cabeceras)


def test_el_reporte_coincide_con_la_fila_del_informe_general(client, cabeceras_admin):
    """Las dos pantallas salen de las mismas definiciones: no pueden discrepar."""
    reporte = _reporte(client, cabeceras_admin).json()
    general = client.get(f"{API}/informes/resumen?{ABRIL}", headers=cabeceras_admin).json()
    fila = next(d for d in general["doctores"] if d["doctor_id"] == 2)

    for campo in ("produccion", "cobrado", "comision", "pagado", "comision_pct"):
        assert Decimal(reporte[campo]) == Decimal(fila[campo]), campo


def test_abril_del_doctor_2(client, cabeceras_admin):
    """El implante: produjo 48 925, se cobraron 25 000 y le toca el 45 % de lo cobrado."""
    reporte = _reporte(client, cabeceras_admin).json()

    assert reporte["doctor_nombre"] == "Miguel Antonio Reyes Peralta"
    assert reporte["produccion"] == "48925.00"
    assert reporte["cobrado"] == "25000.00"
    assert reporte["comision"] == "11250.00"
    assert Decimal(reporte["por_liquidar"]) == Decimal(reporte["comision"]) - Decimal(
        reporte["pagado"]
    )
    assert reporte["consultas"] == 1
    assert reporte["pacientes"] == 1


def test_el_detalle_suma_lo_mismo_que_los_totales(client, cabeceras_admin):
    reporte = _reporte(client, cabeceras_admin, tramo="desde=2026-01-01&hasta=2026-12-31").json()

    assert sum(Decimal(li["total"]) for li in reporte["lineas"]) == Decimal(reporte["produccion"])
    assert sum(Decimal(s["produccion"]) for s in reporte["servicios"]) == Decimal(
        reporte["produccion"]
    )
    assert sum(Decimal(c["monto"]) for c in reporte["cobros"]) == Decimal(reporte["cobrado"])
    assert sum(Decimal(p["monto"]) for p in reporte["pagos"]) == Decimal(reporte["pagado"])
    # De lo que más produjo a lo que menos.
    producciones = [Decimal(s["produccion"]) for s in reporte["servicios"]]
    assert producciones == sorted(producciones, reverse=True)


def test_un_pago_anulado_no_cuenta_como_cobrado(client, cabeceras_admin, cabeceras_recepcion):
    hoy = "desde=2026-01-01&hasta=2031-12-31"
    antes = Decimal(_reporte(client, cabeceras_admin, tramo=hoy).json()["cobrado"])

    # La consulta 2 es del doctor 2 y tiene saldo.
    pago = client.post(
        f"{API}/pacientes/1/pagos",
        headers=cabeceras_recepcion,
        json={"monto": "1000.00", "metodo": "efectivo", "consulta_id": 2},
    )
    assert pago.status_code == 201, pago.text
    assert Decimal(_reporte(client, cabeceras_admin, tramo=hoy).json()["cobrado"]) == antes + 1000

    client.post(
        f"{API}/pagos/{pago.json()['id']}/anular",
        headers=cabeceras_admin,
        json={"motivo": "Cobro duplicado"},
    )
    assert Decimal(_reporte(client, cabeceras_admin, tramo=hoy).json()["cobrado"]) == antes


def test_cada_doctor_ve_el_suyo_y_no_el_de_un_colega(client, cabeceras_doctor, cabeceras_recepcion):
    # `cabeceras_doctor` es la doctora 1.
    assert _reporte(client, cabeceras_doctor, doctor=1).status_code == 200
    ajeno = _reporte(client, cabeceras_doctor, doctor=2)
    assert ajeno.status_code == 403
    assert "tu propio reporte" in ajeno.json()["detail"]
    assert _reporte(client, cabeceras_recepcion, doctor=1).status_code == 403


def test_doctor_inexistente_y_tramo_al_reves(client, cabeceras_admin):
    assert _reporte(client, cabeceras_admin, doctor=999).status_code == 404
    al_reves = _reporte(client, cabeceras_admin, tramo="desde=2026-05-01&hasta=2026-04-01")
    assert al_reves.status_code == 422


def test_un_tramo_sin_actividad_da_ceros(client, cabeceras_admin):
    reporte = _reporte(client, cabeceras_admin, tramo="desde=2020-01-01&hasta=2020-01-31").json()
    assert Decimal(reporte["produccion"]) == 0
    assert Decimal(reporte["comision"]) == 0
    assert reporte["lineas"] == []
    assert reporte["citas"]["total"] == 0
