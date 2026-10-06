"""Reglas del catálogo de servicios que el esquema no puede garantizar."""

import re
import unicodedata

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.catalogo import CondicionDental
from app.models.servicio import CategoriaServicio, ListaPrecio, PrecioServicio, Servicio
from app.schemas.catalogo import PrecioEscribir


def codigo_desde_nombre(db: Session, modelo: type, nombre: str) -> str:
    """Código corto y único derivado del nombre: «Odontopediatría» → ODONT.

    Si ya existe se le añade un número. El código es interno —ordena y prefija—;
    lo que la clínica ve y edita es el nombre.
    """
    plano = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Z0-9]", "", plano.upper())[:5] or "CAT"

    candidato, n = base, 1
    while db.scalar(select(modelo.id).where(modelo.codigo == candidato)) is not None:
        n += 1
        candidato = f"{base}{n}"
    return candidato


def exigir_categoria(db: Session, categoria_id: int) -> CategoriaServicio:
    categoria = db.get(CategoriaServicio, categoria_id)
    if categoria is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La categoría no existe")
    return categoria


def validar_condicion_resultante(db: Session, condicion_id: int | None) -> None:
    """Lo que un servicio pinta al completarse es un tratamiento, no una patología."""
    if condicion_id is None:
        return
    condicion = db.get(CondicionDental, condicion_id)
    if condicion is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "La condición resultante no existe"
        )
    if condicion.patologico:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"«{condicion.nombre}» es un hallazgo, no un tratamiento: un servicio no puede "
            "dejarlo como resultado",
        )


def lista_particular(db: Session) -> ListaPrecio:
    """La tarifa sin aseguradora. Todo servicio debe tener precio en ella."""
    lista = db.scalar(
        select(ListaPrecio)
        .where(ListaPrecio.aseguradora_id.is_(None), ListaPrecio.activo)
        .order_by(ListaPrecio.id)
    )
    if lista is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No hay una tarifa particular activa")
    return lista


def guardar_precios(db: Session, servicio: Servicio, precios: list[PrecioEscribir]) -> None:
    """Fija el precio del servicio en las listas nombradas; las demás no se tocan."""
    vistas: set[int] = set()
    for dato in precios:
        if dato.lista_precio_id in vistas:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "precios: la misma lista aparece dos veces",
            )
        vistas.add(dato.lista_precio_id)

        if db.get(ListaPrecio, dato.lista_precio_id) is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"precios: la lista {dato.lista_precio_id} no existe",
            )

        actual = next(
            (p for p in servicio.precios if p.lista_precio_id == dato.lista_precio_id), None
        )
        if actual is None:
            servicio.precios.append(
                PrecioServicio(
                    lista_precio_id=dato.lista_precio_id,
                    precio=dato.precio,
                    costo=dato.costo or 0,
                    cobertura_pct=dato.cobertura_pct or 0,
                    tasa_impuesto=0,
                )
            )
        else:
            actual.precio = dato.precio
            if dato.costo is not None:
                actual.costo = dato.costo
            if dato.cobertura_pct is not None:
                actual.cobertura_pct = dato.cobertura_pct


def exigir_precio_particular(db: Session, servicio: Servicio) -> None:
    particular = lista_particular(db)
    if not any(p.lista_precio_id == particular.id for p in servicio.precios):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"precios: falta el precio en «{particular.nombre}»",
        )


_USOS = text(
    "SELECT servicio_id FROM procedimiento "
    "UNION SELECT servicio_id FROM plan_item "
    "UNION SELECT servicio_id FROM factura_item "
    "UNION SELECT servicio_id FROM cita WHERE servicio_id IS NOT NULL"
)


def servicios_en_uso(db: Session) -> set[int]:
    """Servicios que ya aparecen en citas, planes, procedimientos o facturas.

    Uno en uso no se borra —se llevaría el histórico—, se desactiva.
    """
    return set(db.execute(_USOS).scalars())
