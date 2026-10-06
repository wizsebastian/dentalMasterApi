"""Comprobantes fiscales con NCF y cierre de caja."""

from decimal import Decimal

API = "/api/v1"


def _facturas(client, cabeceras, paciente=1) -> dict:
    respuesta = client.get(f"{API}/pacientes/{paciente}/facturas", headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


# --- Facturas ------------------------------------------------------------------


def test_facturables_son_las_lineas_sin_comprobante(client, cabeceras_recepcion):
    datos = _facturas(client, cabeceras_recepcion)
    assert len(datos["facturas"]) == 2
    # El procedimiento 6 (6 000) se ejecutó y no está en ninguna factura del seed.
    assert [linea["procedimiento_id"] for linea in datos["facturables"]] == [6]


def test_emitir_toma_el_siguiente_ncf(client, cabeceras_recepcion, sql):
    respuesta = client.post(
        f"{API}/pacientes/1/facturas",
        headers=cabeceras_recepcion,
        json={"procedimiento_ids": [6]},
    )
    assert respuesta.status_code == 201, respuesta.text
    factura = respuesta.json()

    assert factura["numero"] == "B0200000004"
    assert factura["tipo_etiqueta"] == "Consumo"
    assert factura["ncf_vence"] == "2027-12-31"
    assert Decimal(factura["total"]) == Decimal("6000.00")
    assert Decimal(factura["impuesto"]) == 0
    assert factura["razon_social"] == factura["paciente_nombre"]
    assert factura["emisor"]["nombre"]
    assert len(factura["items"]) == 1

    assert sql("SELECT siguiente FROM secuencia_ncf WHERE tipo='B02'").scalar_one() == 5
    assert _facturas(client, cabeceras_recepcion)["facturables"] == []


def test_una_linea_no_se_factura_dos_veces(client, cabeceras_recepcion):
    cuerpo = {"procedimiento_ids": [6]}
    assert (
        client.post(
            f"{API}/pacientes/1/facturas", headers=cabeceras_recepcion, json=cuerpo
        ).status_code
        == 201
    )
    repetida = client.post(f"{API}/pacientes/1/facturas", headers=cabeceras_recepcion, json=cuerpo)
    assert repetida.status_code == 409
    assert "ya está en otro comprobante" in repetida.json()["detail"]


def test_la_factura_respeta_el_descuento_de_la_linea(client, cabeceras_admin, sql):
    # Se anula la factura 2 para volver a facturar sus líneas, que llevan 5 %.
    anulada = client.post(
        f"{API}/facturas/2/anular", headers=cabeceras_admin, json={"motivo": "RNC equivocado"}
    )
    assert anulada.status_code == 200, anulada.text
    assert anulada.json()["estado"] == "anulada"

    lineas = [li["procedimiento_id"] for li in _facturas(client, cabeceras_admin)["facturables"]]
    factura = client.post(
        f"{API}/pacientes/1/facturas",
        headers=cabeceras_admin,
        json={
            "tipo_ncf": "B01",
            "procedimiento_ids": [i for i in lineas if i != 6],
            "rnc_cliente": "1-31-12345-6",
            "razon_social": "Constructora Demo SRL",
        },
    ).json()

    assert factura["numero"] == "B0100000001"
    assert factura["rnc_cliente"] == "131123456"
    assert Decimal(factura["subtotal"]) == Decimal("51500.00")
    assert Decimal(factura["descuento"]) == Decimal("2575.00")
    assert Decimal(factura["total"]) == Decimal("48925.00")


def test_credito_fiscal_exige_rnc(client, cabeceras_recepcion):
    respuesta = client.post(
        f"{API}/pacientes/1/facturas",
        headers=cabeceras_recepcion,
        json={"tipo_ncf": "B01", "procedimiento_ids": [6]},
    )
    assert respuesta.status_code == 422


def test_linea_de_otro_paciente(client, cabeceras_recepcion):
    respuesta = client.post(
        f"{API}/pacientes/2/facturas", headers=cabeceras_recepcion, json={"procedimiento_ids": [6]}
    )
    assert respuesta.status_code == 422


def test_secuencia_agotada_vencida_o_ausente(client, cabeceras_recepcion, sql):
    cuerpo = {"procedimiento_ids": [6]}
    ruta = f"{API}/pacientes/1/facturas"

    sql("UPDATE secuencia_ncf SET vence = '2026-01-01' WHERE tipo = 'B02'")
    assert "venció" in client.post(ruta, headers=cabeceras_recepcion, json=cuerpo).json()["detail"]

    sql("UPDATE secuencia_ncf SET vence = NULL, hasta = 3 WHERE tipo = 'B02'")
    assert "agotada" in client.post(ruta, headers=cabeceras_recepcion, json=cuerpo).json()["detail"]

    sql("UPDATE secuencia_ncf SET activo = FALSE WHERE tipo = 'B02'")
    respuesta = client.post(ruta, headers=cabeceras_recepcion, json=cuerpo)
    assert respuesta.status_code == 409
    assert "No hay una secuencia activa" in respuesta.json()["detail"]


def test_anular_es_de_facturacion_y_no_se_repite(client, cabeceras_recepcion, cabeceras_admin):
    cuerpo = {"motivo": "Emitida por error"}
    assert (
        client.post(
            f"{API}/facturas/3/anular", headers=cabeceras_recepcion, json=cuerpo
        ).status_code
        == 403
    )
    assert (
        client.post(f"{API}/facturas/3/anular", headers=cabeceras_admin, json=cuerpo).status_code
        == 200
    )
    assert (
        client.post(f"{API}/facturas/3/anular", headers=cabeceras_admin, json=cuerpo).status_code
        == 409
    )
    # Sus líneas vuelven a poder facturarse.
    assert len(_facturas(client, cabeceras_admin, paciente=3)["facturables"]) > 0


def test_cargar_una_secuencia_cierra_la_anterior(client, cabeceras_admin, cabeceras_recepcion):
    ruta = f"{API}/secuencias-ncf"
    nueva = {"tipo": "B02", "desde": 501, "hasta": 1000, "vence": "2028-12-31"}
    assert client.post(ruta, headers=cabeceras_recepcion, json=nueva).status_code == 403

    creada = client.post(ruta, headers=cabeceras_admin, json=nueva)
    assert creada.status_code == 201, creada.text
    assert creada.json()["disponibles"] == 500

    secuencias = client.get(ruta, headers=cabeceras_admin).json()
    activas = [s for s in secuencias if s["tipo"] == "B02" and s["activo"]]
    assert [s["desde"] for s in activas] == [501]

    factura = client.post(
        f"{API}/pacientes/1/facturas", headers=cabeceras_recepcion, json={"procedimiento_ids": [6]}
    ).json()
    assert factura["numero"] == "B0200000501"


def test_un_rango_no_puede_pisar_lo_ya_emitido(client, cabeceras_admin):
    rango = {"tipo": "B02", "desde": 2, "hasta": 90}
    respuesta = client.post(f"{API}/secuencias-ncf", headers=cabeceras_admin, json=rango)
    assert respuesta.status_code == 409


# --- Cierre de caja ------------------------------------------------------------


def _pagar(client, cabeceras, monto: str, metodo: str = "efectivo") -> None:
    respuesta = client.post(
        f"{API}/pacientes/1/pagos", headers=cabeceras, json={"monto": monto, "metodo": metodo}
    )
    assert respuesta.status_code == 201, respuesta.text


def test_caja_del_dia_separa_el_efectivo(client, cabeceras_recepcion):
    _pagar(client, cabeceras_recepcion, "1000.00")
    _pagar(client, cabeceras_recepcion, "2500.00", "tarjeta")

    caja = client.get(f"{API}/caja/dia", headers=cabeceras_recepcion).json()
    assert Decimal(caja["cobrado"]) == Decimal("3500.00")
    assert Decimal(caja["efectivo_esperado"]) == Decimal("1000.00")
    assert caja["cierre"] is None


def test_cerrar_caja_guarda_la_foto(client, cabeceras_recepcion):
    _pagar(client, cabeceras_recepcion, "1000.00")

    cierre = client.post(
        f"{API}/caja/cierres", headers=cabeceras_recepcion, json={"efectivo_contado": "1000.00"}
    )
    assert cierre.status_code == 201, cierre.text
    assert Decimal(cierre.json()["diferencia"]) == 0
    assert cierre.json()["cerrado_por_email"] == "recepcion@dentalsonrisa.do"

    # Un cobro posterior no cambia la foto: se ve como movimiento tras el cierre.
    _pagar(client, cabeceras_recepcion, "400.00")
    caja = client.get(f"{API}/caja/dia", headers=cabeceras_recepcion).json()
    assert Decimal(caja["cierre"]["cobrado"]) == Decimal("1000.00")
    assert Decimal(caja["movido_tras_cierre"]) == Decimal("400.00")


def test_un_descuadre_se_explica(client, cabeceras_recepcion):
    _pagar(client, cabeceras_recepcion, "1000.00")
    ruta = f"{API}/caja/cierres"

    sin_nota = client.post(ruta, headers=cabeceras_recepcion, json={"efectivo_contado": "900.00"})
    assert sin_nota.status_code == 422

    con_nota = client.post(
        ruta,
        headers=cabeceras_recepcion,
        json={"efectivo_contado": "900.00", "notas": "Faltan 100: vuelto mal dado"},
    )
    assert con_nota.status_code == 201
    assert Decimal(con_nota.json()["diferencia"]) == Decimal("-100.00")


def test_no_se_cierra_dos_veces_y_solo_admin_reabre(client, cabeceras_recepcion, cabeceras_admin):
    ruta = f"{API}/caja/cierres"
    cierre = client.post(ruta, headers=cabeceras_recepcion, json={"efectivo_contado": "0"}).json()
    assert (
        client.post(ruta, headers=cabeceras_recepcion, json={"efectivo_contado": "0"}).status_code
        == 409
    )
    assert client.delete(f"{ruta}/{cierre['id']}", headers=cabeceras_recepcion).status_code == 403
    assert client.delete(f"{ruta}/{cierre['id']}", headers=cabeceras_admin).status_code == 204
    assert client.get(f"{API}/caja/dia", headers=cabeceras_admin).json()["cierre"] is None
