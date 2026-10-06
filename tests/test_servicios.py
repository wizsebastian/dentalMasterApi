"""Catálogo de servicios, categorías y listas de precio."""

SERVICIOS = "/api/v1/servicios"
CATEGORIAS = "/api/v1/categorias-servicio"

REST = 3  # categoría «Operatoria / Restauradora» del seed
PARTICULAR, ARS = 1, 2  # listas de precio del seed

NUEVO = {
    "categoria_id": REST,
    "nombre": "Incrustación cerámica",
    "requiere_diente": True,
    "duracion_min": 60,
    "precios": [
        {"lista_precio_id": PARTICULAR, "precio": "9500.00", "costo": "4500.00"},
        {"lista_precio_id": ARS, "precio": "8000.00"},
    ],
}


def _id_por_codigo(sql, codigo: str) -> int:
    return sql("SELECT id FROM servicio WHERE codigo = :c", c=codigo).scalar_one()


def test_el_catalogo_trae_el_precio_de_cada_lista(client, cabeceras_doctor):
    """Los precios viven en precio_servicio, no en servicio: uno por lista."""
    cuerpo = client.get(SERVICIOS, headers=cabeceras_doctor).json()

    assert len(cuerpo) == 47
    resina = next(s for s in cuerpo if s["codigo"] == "REST-001")
    assert {p["lista_precio_id"] for p in resina["precios"]} == {PARTICULAR, ARS}
    assert resina["en_uso"] is True
    assert resina["categoria_nombre"] == "Operatoria / Restauradora"


def test_la_particular_va_primero(client, cabeceras_doctor):
    listas = client.get("/api/v1/listas-precio", headers=cabeceras_doctor).json()
    assert [lista["id"] for lista in listas] == [PARTICULAR, ARS]
    assert listas[0]["aseguradora_id"] is None


def test_busqueda_por_nombre_y_por_categoria(client, cabeceras_doctor):
    por_nombre = client.get(f"{SERVICIOS}?buscar=panorámica", headers=cabeceras_doctor).json()
    por_categoria = client.get(f"{SERVICIOS}?categoria_id={REST}", headers=cabeceras_doctor).json()

    assert [s["codigo"] for s in por_nombre] == ["DX-003"]
    assert por_categoria and all(s["categoria_id"] == REST for s in por_categoria)


def test_alta_genera_el_codigo_dentro_de_su_categoria(client, cabeceras_admin, sql):
    """El código sigue al mayor de la categoría aunque la serie no tuviera fila."""
    ultimo = sql(
        "SELECT MAX(substr(codigo, 6)::int) FROM servicio WHERE codigo LIKE 'REST-%'"
    ).scalar_one()

    r = client.post(SERVICIOS, json=NUEVO, headers=cabeceras_admin)

    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["codigo"] == f"REST-{ultimo + 1:03d}"
    assert cuerpo["en_uso"] is False
    assert {p["lista_precio_id"]: p["precio"] for p in cuerpo["precios"]} == {
        PARTICULAR: "9500.00",
        ARS: "8000.00",
    }


def test_sin_precio_particular_no_hay_servicio(client, cabeceras_admin):
    """Todo servicio debe poder cobrarse a un paciente sin seguro."""
    solo_ars = {**NUEVO, "precios": [{"lista_precio_id": ARS, "precio": "8000.00"}]}
    r = client.post(SERVICIOS, json=solo_ars, headers=cabeceras_admin)

    assert r.status_code == 422
    assert "Tarifa particular" in r.json()["detail"]


def test_un_servicio_no_puede_dejar_una_patologia_como_resultado(client, cabeceras_admin, sql):
    caries = sql("SELECT id FROM condicion_dental WHERE codigo = 'CAR'").scalar_one()
    r = client.post(
        SERVICIOS, json={**NUEVO, "condicion_resultante_id": caries}, headers=cabeceras_admin
    )
    assert r.status_code == 422


def test_cambiar_un_precio_no_toca_los_de_las_otras_listas(client, cabeceras_admin, sql):
    servicio_id = _id_por_codigo(sql, "REST-001")
    antes = client.get(f"{SERVICIOS}/{servicio_id}", headers=cabeceras_admin).json()
    ars_antes = next(p for p in antes["precios"] if p["lista_precio_id"] == ARS)

    r = client.patch(
        f"{SERVICIOS}/{servicio_id}",
        json={"precios": [{"lista_precio_id": PARTICULAR, "precio": "3100.00"}]},
        headers=cabeceras_admin,
    )

    assert r.status_code == 200, r.text
    precios = {p["lista_precio_id"]: p for p in r.json()["precios"]}
    assert precios[PARTICULAR]["precio"] == "3100.00"
    assert precios[ARS] == ars_antes


def test_un_servicio_en_uso_se_desactiva_no_se_borra(client, cabeceras_admin, sql):
    """Borrarlo se llevaría el histórico de procedimientos."""
    servicio_id = _id_por_codigo(sql, "REST-001")

    assert client.delete(f"{SERVICIOS}/{servicio_id}", headers=cabeceras_admin).status_code == 409

    r = client.patch(f"{SERVICIOS}/{servicio_id}", json={"activo": False}, headers=cabeceras_admin)
    assert r.json()["activo"] is False
    visibles = client.get(SERVICIOS, headers=cabeceras_admin).json()
    assert servicio_id not in {s["id"] for s in visibles}


def test_un_servicio_sin_uso_se_borra_con_sus_precios(client, cabeceras_admin, sql):
    creado = client.post(SERVICIOS, json=NUEVO, headers=cabeceras_admin).json()

    assert client.delete(f"{SERVICIOS}/{creado['id']}", headers=cabeceras_admin).status_code == 204
    assert (
        sql(
            "SELECT count(*) FROM precio_servicio WHERE servicio_id = :s", s=creado["id"]
        ).scalar_one()
        == 0
    )


def test_el_catalogo_solo_lo_edita_administracion(client, cabeceras_doctor, cabeceras_recepcion):
    assert client.post(SERVICIOS, json=NUEVO, headers=cabeceras_doctor).status_code == 403
    assert client.post(SERVICIOS, json=NUEVO, headers=cabeceras_recepcion).status_code == 403


def test_campo_desconocido_se_rechaza(client, cabeceras_admin):
    r = client.post(SERVICIOS, json={**NUEVO, "precio": 100}, headers=cabeceras_admin)
    assert r.status_code == 422


# --- Categorías ----------------------------------------------------------------


def test_las_categorias_cuentan_sus_servicios(client, cabeceras_doctor):
    categorias = client.get(CATEGORIAS, headers=cabeceras_doctor).json()

    assert len(categorias) == 11
    assert sum(c["servicios"] for c in categorias) == 47


def test_no_caben_dos_categorias_con_el_mismo_nombre(client, cabeceras_admin):
    """La categoría es catálogo, no texto libre: «endodoncia» ya existe."""
    r = client.post(CATEGORIAS, json={"nombre": "endodoncia"}, headers=cabeceras_admin)
    assert r.status_code == 409


def test_alta_de_categoria_deriva_el_codigo(client, cabeceras_admin):
    r = client.post(CATEGORIAS, json={"nombre": "Blanqueamiento"}, headers=cabeceras_admin)

    assert r.status_code == 201, r.text
    assert r.json()["codigo"] == "BLANQ"
    assert r.json()["servicios"] == 0


def test_una_categoria_con_servicios_no_se_borra(client, cabeceras_admin):
    assert client.delete(f"{CATEGORIAS}/{REST}", headers=cabeceras_admin).status_code == 409
