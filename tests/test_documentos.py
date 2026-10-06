"""Plantillas, documentos inmutables, firma por enlace y recetas."""

DOCS = "/api/v1/pacientes/{}/documentos"


def _plantilla(client, cabeceras, codigo):
    return next(
        p
        for p in client.get("/api/v1/plantillas", headers=cabeceras).json()
        if p["codigo"] == codigo
    )


def _emitir(client, cabeceras, paciente_id=1, codigo="CONS-GENERAL", **extra):
    plantilla = _plantilla(client, cabeceras, codigo)
    borrador = client.get(
        f"{DOCS.format(paciente_id)}/borrador?plantilla_id={plantilla['id']}", headers=cabeceras
    ).json()
    return client.post(
        DOCS.format(paciente_id),
        json={
            "tipo": borrador["tipo"],
            "titulo": borrador["titulo"],
            "cuerpo": borrador["cuerpo"],
            "plantilla_id": plantilla["id"],
            "requiere_firma": borrador["requiere_firma"],
            **extra,
        },
        headers=cabeceras,
    )


def test_el_borrador_combina_los_datos_del_paciente(client, cabeceras_recepcion):
    plantilla = _plantilla(client, cabeceras_recepcion, "CONST-VISITA")
    borrador = client.get(
        f"{DOCS.format(3)}/borrador?plantilla_id={plantilla['id']}", headers=cabeceras_recepcion
    ).json()

    assert "Sofía Nicole Martínez Gómez" in borrador["cuerpo"]
    assert "Clínica Dental Sonrisa" in borrador["cuerpo"]
    assert "11 de junio de 2026" in borrador["cuerpo"], "la fecha de su última consulta"
    # La paciente 3 no tiene cédula: el hueco se deja a la vista, no en blanco.
    assert "[paciente: documento]" in borrador["cuerpo"]
    assert "{{" not in borrador["cuerpo"]


def test_un_documento_emitido_guarda_su_texto_y_su_hash(client, cabeceras_recepcion, sql):
    r = _emitir(client, cabeceras_recepcion, codigo="CONST-VISITA")

    assert r.status_code == 201, r.text
    documento = r.json()
    en_base = sql(
        "SELECT encode(digest(cuerpo, 'sha256'), 'hex') FROM documento_emitido WHERE id = :id",
        id=documento["id"],
    ).scalar_one()
    assert documento["sha256"] == en_base
    assert documento["firmas"] == []


def test_cambiar_la_plantilla_no_toca_lo_ya_emitido(client, cabeceras_recepcion, cabeceras_admin):
    documento = _emitir(client, cabeceras_recepcion, codigo="CONST-VISITA").json()
    plantilla = _plantilla(client, cabeceras_admin, "CONST-VISITA")

    client.patch(
        f"/api/v1/plantillas/{plantilla['id']}",
        json={"cuerpo": "Texto nuevo para {{paciente.nombre}}."},
        headers=cabeceras_admin,
    )

    despues = client.get(
        f"/api/v1/documentos/{documento['id']}", headers=cabeceras_recepcion
    ).json()
    assert despues["cuerpo"] == documento["cuerpo"]


def test_una_plantilla_con_una_variable_inventada_se_rechaza(client, cabeceras_admin):
    r = client.post(
        "/api/v1/plantillas",
        json={"tipo": "constancia", "titulo": "Rara", "cuerpo": "Hola {{paciente.apodo}}"},
        headers=cabeceras_admin,
    )
    assert r.status_code == 422
    assert "paciente.apodo" in r.json()["detail"]


def test_firmar_por_enlace_sin_sesion(client, cabeceras_recepcion, sql):
    documento = _emitir(client, cabeceras_recepcion).json()
    token = client.post(
        f"/api/v1/documentos/{documento['id']}/enlace-firma", headers=cabeceras_recepcion
    ).json()["token"]

    # Quien firma no tiene sesión: ve el documento y nada más.
    visto = client.get(f"/api/v1/firma/{token}")
    assert visto.status_code == 200
    assert visto.json()["ya_firmado"] is False
    assert set(visto.json()) == {
        "titulo",
        "cuerpo",
        "paciente_nombre",
        "clinica_nombre",
        "ya_firmado",
    }

    trazo = [[[10, 10], [20, 30], [35, 12], [50, 40], [70, 15], [90, 35], [110, 20], [130, 30]]]
    firmado = client.post(
        f"/api/v1/firma/{token}",
        json={"firmante_nombre": "Juan Carlos Peña Rosario", "trazo": trazo},
    )
    assert firmado.status_code == 204, firmado.text

    despues = client.get(
        f"/api/v1/documentos/{documento['id']}", headers=cabeceras_recepcion
    ).json()
    assert despues["firmas"][0]["firmante_nombre"] == "Juan Carlos Peña Rosario"
    assert (
        sql(
            "SELECT hash_documento FROM firma WHERE documento_emitido_id = :d", d=documento["id"]
        ).scalar_one()
        == documento["sha256"]
    ), "la firma queda atada al texto exacto"

    # El enlace no sirve para firmar dos veces.
    otra = client.post(
        f"/api/v1/firma/{token}", json={"firmante_nombre": "Otra persona", "trazo": trazo}
    )
    assert otra.status_code == 409


def test_una_firma_vacia_no_vale(client, cabeceras_recepcion):
    documento = _emitir(client, cabeceras_recepcion).json()
    token = client.post(
        f"/api/v1/documentos/{documento['id']}/enlace-firma", headers=cabeceras_recepcion
    ).json()["token"]

    r = client.post(
        f"/api/v1/firma/{token}", json={"firmante_nombre": "Juan Peña", "trazo": [[[1, 1], [2, 2]]]}
    )
    assert r.status_code == 422


def test_un_enlace_inventado_o_de_sesion_no_firma(client, cabeceras_recepcion):
    """El token de sesión no vale como enlace de firma, ni al revés."""
    de_sesion = cabeceras_recepcion["Authorization"].removeprefix("Bearer ")
    assert client.get(f"/api/v1/firma/{de_sesion}").status_code == 401
    assert client.get("/api/v1/firma/no-es-un-token").status_code == 401

    documento = _emitir(client, cabeceras_recepcion).json()
    de_firma = client.post(
        f"/api/v1/documentos/{documento['id']}/enlace-firma", headers=cabeceras_recepcion
    ).json()["token"]
    r = client.get("/api/v1/pacientes", headers={"Authorization": f"Bearer {de_firma}"})
    assert r.status_code == 401


def test_el_consentimiento_de_datos_personales_firmado(client, cabeceras_recepcion):
    assert (
        client.get(DOCS.format(2), headers=cabeceras_recepcion).json()["datos_personales_firmados"]
        is False
    )

    documento = _emitir(client, cabeceras_recepcion, paciente_id=2, codigo="CONS-DATOS").json()
    token = client.post(
        f"/api/v1/documentos/{documento['id']}/enlace-firma", headers=cabeceras_recepcion
    ).json()["token"]
    trazo = [[[i * 10, 10 + (i % 2) * 20] for i in range(10)]]
    client.post(
        f"/api/v1/firma/{token}", json={"firmante_nombre": "María Gómez Lantigua", "trazo": trazo}
    )

    assert (
        client.get(DOCS.format(2), headers=cabeceras_recepcion).json()["datos_personales_firmados"]
        is True
    )


def test_anular_un_documento_no_lo_borra(client, cabeceras_recepcion):
    documento = _emitir(client, cabeceras_recepcion).json()
    r = client.post(
        f"/api/v1/documentos/{documento['id']}/anular",
        json={"motivo": "Se emitió con el doctor equivocado"},
        headers=cabeceras_recepcion,
    )

    assert r.json()["anulado_en"] is not None
    ids = {
        d["id"]
        for d in client.get(DOCS.format(1), headers=cabeceras_recepcion).json()["documentos"]
    }
    assert documento["id"] in ids
    # Y ya no se puede firmar.
    enlace = client.post(
        f"/api/v1/documentos/{documento['id']}/enlace-firma", headers=cabeceras_recepcion
    )
    assert enlace.status_code == 409


# --- Recetas -------------------------------------------------------------------

RECETA = {
    "doctor_id": 1,
    "indicaciones": "Tomar con alimentos.",
    "items": [
        {"medicamento": "Ibuprofeno 400 mg", "dosis": "1 tableta", "frecuencia": "Cada 8 horas"}
    ],
}


def test_recetar(client, cabeceras_doctor):
    """El paciente 2 sólo es alérgico al látex."""
    r = client.post("/api/v1/pacientes/2/recetas", json=RECETA, headers=cabeceras_doctor)

    assert r.status_code == 201, r.text
    assert r.json()["items"][0]["medicamento"] == "Ibuprofeno 400 mg"
    recetas = client.get(DOCS.format(2), headers=cabeceras_doctor).json()["recetas"]
    assert len(recetas) == 1


def test_recetar_contra_una_alergia_exige_confirmarlo(client, cabeceras_doctor):
    """El paciente 1 es alérgico a la penicilina: la amoxicilina choca aunque no se llame igual."""
    amoxicilina = {
        **RECETA,
        "items": [
            {
                "medicamento": "Amoxicilina 500 mg",
                "dosis": "1 cápsula",
                "frecuencia": "Cada 8 horas",
            }
        ],
    }

    r = client.post("/api/v1/pacientes/1/recetas", json=amoxicilina, headers=cabeceras_doctor)
    assert r.status_code == 409
    assert "Penicilina" in r.json()["detail"]

    confirmada = client.post(
        "/api/v1/pacientes/1/recetas",
        json={**amoxicilina, "confirmar_alergias": True},
        headers=cabeceras_doctor,
    )
    assert confirmada.status_code == 201


def test_recepcion_no_receta(client, cabeceras_recepcion):
    r = client.post("/api/v1/pacientes/2/recetas", json=RECETA, headers=cabeceras_recepcion)
    assert r.status_code == 403
