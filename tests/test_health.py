def test_health_responde_con_el_catalogo_cargado(client):
    respuesta = client.get("/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok", "dientes_en_catalogo": 52}
