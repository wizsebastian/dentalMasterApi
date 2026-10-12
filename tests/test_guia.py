"""La guía interactiva: vista pública que guarda, análisis sólo para administración."""

import pytest

from app.api.v1.routers import guia


@pytest.fixture(autouse=True)
def _sin_limites_previos():
    for dep in (guia.limite_altas, guia.limite_escrituras, guia.limite_lecturas):
        dep.registro.clear()
    yield
    for dep in (guia.limite_altas, guia.limite_escrituras, guia.limite_lecturas):
        dep.registro.clear()


def _abrir(client, nombre="Dr. Prueba"):
    r = client.post("/api/v1/guia/sesiones", json={"nombre": nombre, "rol": "doctor"})
    assert r.status_code == 201, r.text
    return r.json()["codigo"]


def test_sesion_se_crea_y_se_retoma_sin_sesion(client):
    codigo = _abrir(client)
    r = client.get(f"/api/v1/guia/sesiones/{codigo}")
    assert r.status_code == 200
    assert r.json()["nombre"] == "Dr. Prueba"
    assert r.json()["respuestas"] == []


def test_guardar_un_paso_deja_respuesta_y_bitacora(client, cabeceras_admin):
    codigo = _abrir(client)
    url = f"/api/v1/guia/sesiones/{codigo}/pasos/doc-1"
    assert client.put(url, json={"estado": "duda", "nota": "no entiendo X"}).status_code == 200
    r = client.put(url, json={"estado": "ok", "nota": "ya lo entendí"})
    assert r.json()["respuestas"][0]["estado"] == "ok"
    # Repetir lo mismo no ensucia la bitácora.
    client.put(url, json={"estado": "ok", "nota": "ya lo entendí"})

    export = client.get("/api/v1/guia/exportar", headers=cabeceras_admin).json()
    mia = next(s for s in export if s["codigo"] == codigo)
    assert [e["estado"] for e in mia["eventos"]] == ["duda", "ok"]


def test_datos_invalidos_se_rechazan(client):
    codigo = _abrir(client)
    base = f"/api/v1/guia/sesiones/{codigo}"
    assert client.put(f"{base}/pasos/doc-1", json={"estado": "quizas"}).status_code == 422
    assert client.put(f"{base}/pasos/DOC 1!", json={"estado": "ok"}).status_code == 422
    assert client.put(f"{base}/pasos/doc-1", json={"estado": "ok", "x": 1}).status_code == 422
    larga = {"estado": "ok", "nota": "a" * 4001}
    assert client.put(f"{base}/pasos/doc-1", json=larga).status_code == 422
    assert client.post("/api/v1/guia/sesiones", json={"nombre": "x"}).status_code == 422


def test_sesion_inexistente_es_404(client):
    assert client.get("/api/v1/guia/sesiones/no-existe").status_code == 404
    r = client.put("/api/v1/guia/sesiones/no-existe/pasos/doc-1", json={"estado": "ok"})
    assert r.status_code == 404


def test_impresion_general(client):
    codigo = _abrir(client)
    r = client.put(f"/api/v1/guia/sesiones/{codigo}/general", json={"texto": "  Muy claro  "})
    assert r.json()["impresion_general"] == "Muy claro"


def test_el_analisis_pide_administracion(client, cabeceras_admin, cabeceras_doctor):
    codigo = _abrir(client)
    client.put(f"/api/v1/guia/sesiones/{codigo}/pasos/doc-1", json={"estado": "falla"})
    for ruta in ("resumen", "exportar"):
        assert client.get(f"/api/v1/guia/{ruta}").status_code == 401
        assert client.get(f"/api/v1/guia/{ruta}", headers=cabeceras_doctor).status_code == 403
    r = client.get("/api/v1/guia/resumen", headers=cabeceras_admin)
    assert r.status_code == 200
    assert any(p["paso_id"] == "doc-1" and p["falla"] >= 1 for p in r.json()["pasos"])


def test_el_limite_por_direccion_responde_429(client):
    for _ in range(10):
        _abrir(client)
    r = client.post("/api/v1/guia/sesiones", json={"nombre": "Otro más"})
    assert r.status_code == 429
