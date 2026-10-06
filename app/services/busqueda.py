"""Búsqueda de texto sin tildes ni mayúsculas.

«gomez» debe encontrar «Gómez»: en un mostrador nadie teclea las tildes. Lo hace
la extensión `unaccent` de Postgres (declarada en `01_schema.sql`), y el
navegador hace lo mismo en los filtros que corren de su lado
(`src/lib/texto.ts`).
"""

import re

from sqlalchemy import ColumnElement, func, literal


def coincide(columna: ColumnElement, texto: str) -> ColumnElement[bool]:
    """`columna` contiene `texto`, ignorando tildes y mayúsculas."""
    patron = f"%{texto.strip()}%"
    return func.unaccent(columna).ilike(func.unaccent(literal(patron)))


def digitos_de(texto: str) -> str:
    return re.sub(r"\D", "", texto)


def coincide_digitos(columna: ColumnElement, texto: str) -> ColumnElement[bool] | None:
    """Para teléfonos: compara sólo los dígitos, así `7770002` encuentra
    `(809) 777-0002`. Devuelve `None` si lo buscado no tiene suficientes dígitos
    para que valga la pena (un nombre no debe encontrar teléfonos)."""
    digitos = digitos_de(texto)
    if len(digitos) < 4:
        return None
    return func.regexp_replace(columna, r"\D", "", "g").like(f"%{digitos}%")
