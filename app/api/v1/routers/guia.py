"""Guía interactiva (`/guia`): la vista pública donde quien prueba el sistema marca y escribe.

Sin sesión, como la firma por enlace: quien tiene el código de su sesión escribe
en ella y en ninguna otra. Lo abierto se acota con un límite por dirección y con
topes de tamaño. El análisis (`resumen`, `exportar`) es sólo de administración.
"""

import re
import secrets
from ipaddress import ip_address
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import BD, requiere_rol
from app.core.limite import ip_de, limitar
from app.models.guia import GuiaEvento, GuiaRespuesta, GuiaSesion
from app.models.organizacion import Usuario
from app.schemas.guia import (
    GuiaGeneralEscribir,
    GuiaPasoEscribir,
    GuiaPasoResumen,
    GuiaResumen,
    GuiaSesionCrear,
    GuiaSesionExportada,
    GuiaSesionLeer,
    GuiaSesionResumen,
)

router = APIRouter(prefix="/guia", tags=["guia"])

PuedeAnalizar = Annotated[Usuario, Depends(requiere_rol())]

limite_altas = limitar("altas", maximo=10, ventana_s=3600)
limite_escrituras = limitar("escrituras", maximo=120, ventana_s=60)
limite_lecturas = limitar("lecturas", maximo=120, ventana_s=60)

# Un paso se nombra como en `features/guia/contenido.ts`: `onb-1`, `doc-12`…
PASO_ID = r"^[a-z0-9][a-z0-9_-]{0,39}$"


def _sesion(db: Session, codigo: str) -> GuiaSesion:
    sesion = db.scalar(
        select(GuiaSesion)
        .where(GuiaSesion.codigo == codigo)
        .options(selectinload(GuiaSesion.respuestas))
    )
    if sesion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La sesión de la guía no existe")
    return sesion


def _ip(request: Request) -> str | None:
    try:
        return str(ip_address(ip_de(request)))
    except ValueError:
        return None


@router.post(
    "/sesiones",
    response_model=GuiaSesionLeer,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limite_altas)],
)
def crear_sesion(datos: GuiaSesionCrear, request: Request, db: BD) -> GuiaSesion:
    sesion = GuiaSesion(
        codigo=secrets.token_urlsafe(9),
        nombre=datos.nombre.strip(),
        rol=(datos.rol or "").strip() or None,
        ip=_ip(request),
        dispositivo=(request.headers.get("user-agent") or "")[:300] or None,
    )
    db.add(sesion)
    db.commit()
    return _sesion(db, sesion.codigo)


@router.get(
    "/sesiones/{codigo}",
    response_model=GuiaSesionLeer,
    dependencies=[Depends(limite_lecturas)],
)
def leer_sesion(codigo: str, db: BD) -> GuiaSesion:
    return _sesion(db, codigo)


@router.put(
    "/sesiones/{codigo}/pasos/{paso_id}",
    response_model=GuiaSesionLeer,
    dependencies=[Depends(limite_escrituras)],
)
def guardar_paso(codigo: str, paso_id: str, datos: GuiaPasoEscribir, db: BD) -> GuiaSesion:
    if not re.fullmatch(PASO_ID, paso_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "paso_id: formato no válido")
    sesion = _sesion(db, codigo)
    nota = datos.nota.strip()
    actual = next((r for r in sesion.respuestas if r.paso_id == paso_id), None)

    if actual is not None and actual.estado == datos.estado and actual.nota == nota:
        return sesion

    if actual is None:
        db.add(GuiaRespuesta(sesion_id=sesion.id, paso_id=paso_id, estado=datos.estado, nota=nota))
    else:
        actual.estado = datos.estado
        actual.nota = nota
        actual.actualizado_en = func.now()
    db.add(GuiaEvento(sesion_id=sesion.id, paso_id=paso_id, estado=datos.estado, nota=nota))
    sesion.actualizado_en = func.now()
    db.commit()
    db.expire_all()
    return _sesion(db, codigo)


@router.put(
    "/sesiones/{codigo}/general",
    response_model=GuiaSesionLeer,
    dependencies=[Depends(limite_escrituras)],
)
def guardar_general(codigo: str, datos: GuiaGeneralEscribir, db: BD) -> GuiaSesion:
    sesion = _sesion(db, codigo)
    sesion.impresion_general = datos.texto.strip()
    sesion.actualizado_en = func.now()
    db.commit()
    db.expire_all()
    return _sesion(db, codigo)


@router.get("/resumen", response_model=GuiaResumen)
def resumen(_: PuedeAnalizar, db: BD) -> GuiaResumen:
    """Quién va por dónde y en qué pasos se atasca la gente."""
    sesiones = []
    for s in db.scalars(
        select(GuiaSesion)
        .options(selectinload(GuiaSesion.respuestas))
        .order_by(GuiaSesion.actualizado_en.desc())
    ):
        cuenta = {e: sum(1 for r in s.respuestas if r.estado == e) for e in ("ok", "falla", "duda")}
        sesiones.append(
            GuiaSesionResumen(
                codigo=s.codigo,
                nombre=s.nombre,
                rol=s.rol,
                creado_en=s.creado_en,
                actualizado_en=s.actualizado_en,
                notas=sum(1 for r in s.respuestas if r.nota),
                **cuenta,
            )
        )
    filas = db.execute(
        select(
            GuiaRespuesta.paso_id,
            func.count().filter(GuiaRespuesta.estado == "ok"),
            func.count().filter(GuiaRespuesta.estado == "falla"),
            func.count().filter(GuiaRespuesta.estado == "duda"),
        )
        .group_by(GuiaRespuesta.paso_id)
        .order_by(GuiaRespuesta.paso_id)
    ).all()
    return GuiaResumen(
        sesiones=sesiones,
        pasos=[GuiaPasoResumen(paso_id=p, ok=o, falla=f, duda=d) for p, o, f, d in filas],
    )


@router.get("/exportar", response_model=list[GuiaSesionExportada])
def exportar(_: PuedeAnalizar, db: BD) -> list[dict]:
    """Todo lo registrado, con la bitácora de cambios de cada sesión."""
    salida = []
    for s in db.scalars(
        select(GuiaSesion)
        .options(selectinload(GuiaSesion.respuestas))
        .order_by(GuiaSesion.creado_en)
    ):
        eventos = db.scalars(
            select(GuiaEvento).where(GuiaEvento.sesion_id == s.id).order_by(GuiaEvento.id)
        ).all()
        salida.append(
            {
                **GuiaSesionLeer.model_validate(s).model_dump(),
                "eventos": eventos,
            }
        )
    return salida
