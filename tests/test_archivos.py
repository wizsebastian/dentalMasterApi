"""Archivos: subida, tipo por contenido, descarga y comprobantes."""

import pytest

from app.core.config import settings

API = "/api/v1"

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x01" * 64
PDF = b"%PDF-1.7\n" + b"\x02" * 64


@pytest.fixture(autouse=True)
def almacen_temporal(tmp_path, monkeypatch):
    """La base se revierte al acabar el test; el disco no. Cada test usa el suyo."""
    monkeypatch.setattr(settings, "almacen_dir", str(tmp_path))
    return tmp_path


def _subir(client, cabeceras, contenido=PNG, nombre="intraoral.png", **campos):
    return client.post(
        f"{API}/pacientes/1/archivos",
        headers=cabeceras,
        files={"archivo": (nombre, contenido, "application/octet-stream")},
        data=campos,
    )


def test_subir_foto_de_consulta(client, cabeceras_doctor, almacen_temporal):
    respuesta = _subir(client, cabeceras_doctor, consulta_id=2, titulo="  Lecho quirúrgico ")
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()

    assert cuerpo["tipo"] == "foto"
    assert cuerpo["titulo"] == "Lecho quirúrgico"
    assert cuerpo["consulta_id"] == 2
    # El tipo sale de los bytes, no de lo que declaró el navegador.
    assert cuerpo["archivo"]["mime"] == "image/png"
    assert cuerpo["archivo"]["bytes"] == len(PNG)
    assert len([p for p in almacen_temporal.rglob("*") if p.is_file()]) == 1


def test_descargar_devuelve_los_mismos_bytes(client, cabeceras_doctor, cabeceras_recepcion):
    archivo_id = _subir(client, cabeceras_doctor, JPG, "foto.jpg").json()["archivo"]["id"]

    respuesta = client.get(f"{API}/archivos/{archivo_id}", headers=cabeceras_recepcion)
    assert respuesta.status_code == 200
    assert respuesta.content == JPG
    assert respuesta.headers["content-type"] == "image/jpeg"
    assert respuesta.headers["x-content-type-options"] == "nosniff"


def test_descargar_exige_sesion(client, cabeceras_doctor):
    archivo_id = _subir(client, cabeceras_doctor).json()["archivo"]["id"]
    assert client.get(f"{API}/archivos/{archivo_id}").status_code == 401


def test_rechaza_lo_que_no_es_imagen_ni_pdf(client, cabeceras_doctor, almacen_temporal):
    respuesta = _subir(client, cabeceras_doctor, b"<html><script>alert(1)</script>", "foto.png")
    assert respuesta.status_code == 415
    assert not [p for p in almacen_temporal.rglob("*") if p.is_file()]


def test_rechaza_archivo_vacio(client, cabeceras_doctor):
    assert _subir(client, cabeceras_doctor, b"").status_code == 422


def test_rechaza_archivo_demasiado_grande(client, cabeceras_doctor, monkeypatch, almacen_temporal):
    monkeypatch.setattr(settings, "archivo_max_mb", 1)
    respuesta = _subir(client, cabeceras_doctor, PNG + b"\x00" * (1024 * 1024))
    assert respuesta.status_code == 413
    assert not [p for p in almacen_temporal.rglob("*") if p.is_file()]


def test_consulta_de_otro_paciente(client, cabeceras_doctor):
    # La consulta 3 es del paciente 3.
    assert _subir(client, cabeceras_doctor, consulta_id=3).status_code == 422


def test_listar_filtra_por_consulta(client, cabeceras_doctor):
    _subir(client, cabeceras_doctor, consulta_id=2)
    _subir(client, cabeceras_doctor, PDF, "analitica.pdf", tipo="laboratorio")

    todos = client.get(f"{API}/pacientes/1/archivos", headers=cabeceras_doctor).json()
    de_la_consulta = client.get(
        f"{API}/pacientes/1/archivos?consulta_id=2", headers=cabeceras_doctor
    ).json()

    # Cuatro referencias del seed más las dos subidas.
    assert len(todos) == 6
    assert {d["tipo"] for d in todos} >= {"foto", "laboratorio", "panoramica"}
    assert [d["archivo"] is not None for d in de_la_consulta].count(True) == 1


def test_actualizar_y_quitar(client, cabeceras_doctor, cabeceras_recepcion, almacen_temporal):
    documento = _subir(client, cabeceras_doctor).json()

    editado = client.patch(
        f"{API}/archivos-clinicos/{documento['id']}",
        headers=cabeceras_recepcion,
        json={"tipo": "radiografia_periapical", "codigo_fdi": 36, "tomado_en": "2026-09-30"},
    )
    assert editado.status_code == 200, editado.text
    assert editado.json()["codigo_fdi"] == 36

    # Quitar un examen es cosa del doctor.
    ruta = f"{API}/archivos-clinicos/{documento['id']}"
    assert client.delete(ruta, headers=cabeceras_recepcion).status_code == 403
    assert client.delete(ruta, headers=cabeceras_doctor).status_code == 204
    assert not [p for p in almacen_temporal.rglob("*") if p.is_file()]


def test_el_mismo_archivo_dos_veces_comparte_bytes(client, cabeceras_doctor, almacen_temporal):
    primero = _subir(client, cabeceras_doctor).json()
    segundo = _subir(client, cabeceras_doctor).json()
    assert primero["archivo"]["id"] != segundo["archivo"]["id"]
    assert len([p for p in almacen_temporal.rglob("*") if p.is_file()]) == 1

    # Quitar uno no deja al otro sin contenido.
    client.delete(f"{API}/archivos-clinicos/{primero['id']}", headers=cabeceras_doctor)
    descarga = client.get(f"{API}/archivos/{segundo['archivo']['id']}", headers=cabeceras_doctor)
    assert descarga.status_code == 200


def test_comprobante_de_pago(client, cabeceras_recepcion):
    subido = client.put(
        f"{API}/pagos/1/comprobante",
        headers=cabeceras_recepcion,
        files={"archivo": ("voucher.jpg", JPG, "image/jpeg")},
    )
    assert subido.status_code == 200, subido.text

    pago = client.get(f"{API}/pagos/1", headers=cabeceras_recepcion).json()
    assert pago["comprobante_id"] == subido.json()["id"]

    assert (
        client.delete(f"{API}/pagos/1/comprobante", headers=cabeceras_recepcion).status_code == 204
    )
    assert (
        client.get(f"{API}/pagos/1", headers=cabeceras_recepcion).json()["comprobante_id"] is None
    )


def test_comprobante_de_gasto_sustituye_al_anterior(client, cabeceras_admin, almacen_temporal):
    for contenido in (JPG, PDF):
        respuesta = client.put(
            f"{API}/gastos/1/comprobante",
            headers=cabeceras_admin,
            files={"archivo": ("factura", contenido, "application/octet-stream")},
        )
        assert respuesta.status_code == 200, respuesta.text

    assert respuesta.json()["mime"] == "application/pdf"
    assert len([p for p in almacen_temporal.rglob("*") if p.is_file()]) == 1


def test_recepcion_no_adjunta_a_gastos(client, cabeceras_recepcion):
    respuesta = client.put(
        f"{API}/gastos/1/comprobante",
        headers=cabeceras_recepcion,
        files={"archivo": ("factura.pdf", PDF, "application/pdf")},
    )
    assert respuesta.status_code == 403
