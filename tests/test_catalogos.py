"""Catálogos que alimentan el odontograma."""

RUTA = "/api/v1/catalogos/odontograma"


def test_devuelve_las_tres_piezas_en_una_llamada(client, cabeceras_doctor):
    cuerpo = client.get(RUTA, headers=cabeceras_doctor).json()

    assert len(cuerpo["dientes"]) == 52
    assert len(cuerpo["superficies"]) == 6
    assert len(cuerpo["condiciones"]) == 35


def test_el_centro_de_la_pieza_distingue_incisal_de_oclusal(client, cabeceras_doctor):
    """El frontend necesita saber si el centro del diente es 'I' u 'O'."""
    dientes = {
        d["codigo_fdi"]: d for d in client.get(RUTA, headers=cabeceras_doctor).json()["dientes"]
    }

    assert dientes[11]["centro_oclusal"] == "I"  # incisivo central
    assert dientes[13]["centro_oclusal"] == "I"  # canino
    assert dientes[16]["centro_oclusal"] == "O"  # molar
    assert dientes[14]["centro_oclusal"] == "O"  # premolar


def test_las_condiciones_traen_color(client, cabeceras_doctor):
    """Es el único origen del color: el frontend no lo escribe a mano."""
    condiciones = client.get(RUTA, headers=cabeceras_doctor).json()["condiciones"]

    assert all(c["color_hex"].startswith("#") and len(c["color_hex"]) == 7 for c in condiciones)
    caries = next(c for c in condiciones if c["codigo"] == "CAR")
    assert caries["color_hex"] == "#E53935"
    assert caries["patologico"] is True


def test_el_catalogo_exige_sesion(client):
    assert client.get(RUTA).status_code == 401
