"""Búsqueda sin tildes, teléfonos con formato y datos de la clínica (con su logo)."""

import pytest

from app.core.config import settings

API = "/api/v1"

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"\x02" * 64


@pytest.fixture(autouse=True)
def almacen_temporal(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "almacen_dir", str(tmp_path))
    return tmp_path


# --- Búsqueda sin tildes ---------------------------------------------------------


def _ids(client, cabeceras, ruta):
    return [p["id"] for p in client.get(ruta, headers=cabeceras).json()["items"]]


@pytest.mark.parametrize("buscado", ["gomez", "GÓMEZ", "gómez", "altagracia gomez", "maria"])
def test_los_pacientes_se_encuentran_sin_tildes(client, cabeceras_recepcion, buscado):
    # María Altagracia Gómez Lantigua es el paciente 2; «Sofía Nicole Martínez Gómez», el 3.
    ids = _ids(client, cabeceras_recepcion, f"{API}/pacientes?buscar={buscado}")
    assert 2 in ids


def test_pena_encuentra_pena_con_enie(client, cabeceras_recepcion):
    assert _ids(client, cabeceras_recepcion, f"{API}/pacientes?buscar=pena") == [1]
    assert _ids(client, cabeceras_recepcion, f"{API}/pacientes?buscar=Peña") == [1]


def test_un_telefono_se_encuentra_por_sus_digitos(client, cabeceras_recepcion):
    for buscado in ("7770002", "777-0002", "(809) 777-0002", "8097770002"):
        assert _ids(client, cabeceras_recepcion, f"{API}/pacientes?buscar={buscado}") == [
            2
        ], buscado


def test_un_nombre_no_encuentra_telefonos(client, cabeceras_recepcion):
    assert _ids(client, cabeceras_recepcion, f"{API}/pacientes?buscar=zzzz") == []


def test_los_servicios_se_buscan_sin_tildes(client, cabeceras_recepcion):
    nombres = [
        s["nombre"]
        for s in client.get(
            f"{API}/servicios?buscar=radiografia", headers=cabeceras_recepcion
        ).json()
    ]
    assert any("panorámica" in n.lower() for n in nombres)


def test_los_gastos_se_buscan_sin_tildes(client, cabeceras_admin):
    respuesta = client.get(
        f"{API}/gastos?desde=2026-01-01&hasta=2026-12-31&buscar=deposito", headers=cabeceras_admin
    )
    assert respuesta.status_code == 200, respuesta.text
    assert len(respuesta.json()["items"]) >= 1


def test_las_cuentas_por_cobrar_se_buscan_sin_tildes_y_por_telefono(client, cabeceras_recepcion):
    por_nombre = client.get(f"{API}/cuentas-por-cobrar?buscar=pena", headers=cabeceras_recepcion)
    por_telefono = client.get(
        f"{API}/cuentas-por-cobrar?buscar=7770001", headers=cabeceras_recepcion
    )
    assert [i["paciente_id"] for i in por_nombre.json()["items"]] == [1]
    assert [i["paciente_id"] for i in por_telefono.json()["items"]] == [1]


# --- Teléfonos -------------------------------------------------------------------


@pytest.mark.parametrize(
    "escrito", ["8095550100", "809-555-0100", "(809) 555-0100", "+1 809 555 0100", "1-809-555-0100"]
)
def test_el_telefono_se_guarda_siempre_igual(client, cabeceras_recepcion, escrito):
    respuesta = client.post(
        f"{API}/pacientes",
        headers=cabeceras_recepcion,
        json={"nombres": "Tel", "apellidos": "Prueba", "celular": escrito, "telefono": escrito},
    )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["celular"] == "(809) 555-0100"
    assert respuesta.json()["telefono"] == "(809) 555-0100"


@pytest.mark.parametrize("malo", ["555-0100", "80955501", "12345678901234"])
def test_un_telefono_incompleto_se_rechaza(client, cabeceras_recepcion, malo):
    respuesta = client.post(
        f"{API}/pacientes",
        headers=cabeceras_recepcion,
        json={"nombres": "Tel", "apellidos": "Malo", "celular": malo},
    )
    assert respuesta.status_code == 422
    assert "10 dígitos" in respuesta.text


def test_un_telefono_vacio_es_valido_y_borra(client, cabeceras_recepcion):
    respuesta = client.patch(
        f"{API}/pacientes/1", headers=cabeceras_recepcion, json={"telefono": "  "}
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["telefono"] is None


# --- La clínica ------------------------------------------------------------------


def test_la_clinica_trae_whatsapp_web_y_logo(client, cabeceras_recepcion):
    cuerpo = client.get(f"{API}/catalogos/clinica", headers=cabeceras_recepcion).json()
    assert cuerpo["whatsapp"] == "(809) 555-0101"
    assert cuerpo["web"] == "www.dentalsonrisa.do"
    assert cuerpo["logo_archivo_id"] is None


def test_solo_administracion_edita_la_clinica(
    client, cabeceras_admin, cabeceras_recepcion, cabeceras_doctor
):
    cuerpo = {"nombre": "Clínica Sonrisa Plus"}
    for cabeceras in (cabeceras_recepcion, cabeceras_doctor):
        assert (
            client.patch(f"{API}/catalogos/clinica", headers=cabeceras, json=cuerpo).status_code
            == 403
        )

    editada = client.patch(
        f"{API}/catalogos/clinica",
        headers=cabeceras_admin,
        json={
            **cuerpo,
            "whatsapp": "829 555 0188",
            "email": "hola@sonrisa.do",
            "web": "sonrisa.do",
        },
    )
    assert editada.status_code == 200, editada.text
    assert editada.json()["nombre"] == "Clínica Sonrisa Plus"
    assert editada.json()["whatsapp"] == "(829) 555-0188"

    # Lo que cambió lo ve todo el sistema: recibo, recordatorios y plantillas.
    leida = client.get(f"{API}/catalogos/clinica", headers=cabeceras_recepcion).json()
    assert leida["nombre"] == "Clínica Sonrisa Plus"


def test_la_clinica_valida_lo_que_recibe(client, cabeceras_admin):
    assert (
        client.patch(
            f"{API}/catalogos/clinica", headers=cabeceras_admin, json={"nombre": ""}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{API}/catalogos/clinica", headers=cabeceras_admin, json={"nombre": None}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{API}/catalogos/clinica", headers=cabeceras_admin, json={"telefono": "123"}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{API}/catalogos/clinica", headers=cabeceras_admin, json={"email": "no-es-correo"}
        ).status_code
        == 422
    )


def test_el_logo_se_sube_se_lee_y_se_quita(
    client, cabeceras_admin, cabeceras_recepcion, almacen_temporal
):
    subido = client.put(
        f"{API}/catalogos/clinica/logo",
        headers=cabeceras_admin,
        files={"archivo": ("logo.png", PNG, "application/octet-stream")},
    )
    assert subido.status_code == 200, subido.text
    logo = subido.json()["logo_archivo_id"]
    assert logo is not None

    # Cualquiera con sesión lo pide: lo llevan todos los impresos.
    descarga = client.get(f"{API}/archivos/{logo}", headers=cabeceras_recepcion)
    assert descarga.status_code == 200
    assert descarga.content == PNG

    assert (
        client.delete(f"{API}/catalogos/clinica/logo", headers=cabeceras_admin).status_code == 204
    )
    assert (
        client.get(f"{API}/catalogos/clinica", headers=cabeceras_admin).json()["logo_archivo_id"]
        is None
    )
    assert not [p for p in almacen_temporal.rglob("*") if p.is_file()]


def test_el_logo_nuevo_sustituye_al_anterior(client, cabeceras_admin, almacen_temporal):
    for contenido in (PNG, PNG + b"\x01"):
        respuesta = client.put(
            f"{API}/catalogos/clinica/logo",
            headers=cabeceras_admin,
            files={"archivo": ("logo.png", contenido, "application/octet-stream")},
        )
        assert respuesta.status_code == 200
    assert len([p for p in almacen_temporal.rglob("*") if p.is_file()]) == 1


def test_un_logo_no_puede_ser_un_pdf_ni_lo_sube_recepcion(
    client, cabeceras_admin, cabeceras_recepcion
):
    pdf = client.put(
        f"{API}/catalogos/clinica/logo",
        headers=cabeceras_admin,
        files={"archivo": ("logo.pdf", PDF, "application/pdf")},
    )
    assert pdf.status_code == 415

    ajeno = client.put(
        f"{API}/catalogos/clinica/logo",
        headers=cabeceras_recepcion,
        files={"archivo": ("logo.png", PNG, "image/png")},
    )
    assert ajeno.status_code == 403


def test_las_plantillas_conocen_el_contacto_de_la_clinica(client, cabeceras_doctor):
    borrador = client.get(
        f"{API}/pacientes/1/documentos/borrador?plantilla_id=1", headers=cabeceras_doctor
    )
    assert borrador.status_code == 200, borrador.text
