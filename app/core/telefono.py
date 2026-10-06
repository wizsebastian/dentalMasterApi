"""Teléfonos: siempre `(809) 555-0100`, sea como sea que se tecleen."""

import re
from typing import Annotated

from pydantic import AfterValidator

DIGITOS = 10


def normalizar_telefono(valor: str | None) -> str | None:
    """Vacío es válido (el teléfono casi siempre es opcional); lo demás debe ser
    un número de diez dígitos, con o sin el 1 inicial de país."""
    if valor is None:
        return None
    valor = valor.strip()
    if not valor:
        return None

    digitos = re.sub(r"\D", "", valor)
    if len(digitos) == DIGITOS + 1 and digitos.startswith("1"):
        digitos = digitos[1:]
    if len(digitos) != DIGITOS:
        raise ValueError("El teléfono debe tener 10 dígitos, por ejemplo (809) 555-0100")
    return f"({digitos[:3]}) {digitos[3:6]}-{digitos[6:]}"


# Para los campos de los schemas: `telefono: Telefono = None`.
Telefono = Annotated[str | None, AfterValidator(normalizar_telefono)]
