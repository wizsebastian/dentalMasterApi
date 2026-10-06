"""Almacén de archivos: fotos, exámenes y comprobantes.

Los bytes viven en un volumen, fuera de la base, direccionados por contenido:
la ruta es el sha256 (`ab/cd/abcd…`). La base sólo guarda el hash, así que
mover el almacén a otro disco —o a un servicio de objetos— no toca ninguna fila:
basta con cambiar las tres funciones de abajo.
"""

import hashlib
import os
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.archivo import Archivo
from app.models.organizacion import Usuario

TROZO = 1024 * 1024

# El tipo se decide por los primeros bytes, no por lo que diga el navegador ni
# por la extensión: es lo que después se sirve como Content-Type.
_FIRMAS: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"%PDF-", "application/pdf"),
)


def tipo_de(cabecera: bytes) -> str | None:
    for firma, mime in _FIRMAS:
        if cabecera.startswith(firma):
            return mime
    if cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP":
        return "image/webp"
    return None


def ruta(sha256: str) -> Path:
    return Path(settings.almacen_dir) / sha256[:2] / sha256[2:4] / sha256


IMAGENES = ("image/jpeg", "image/png", "image/webp")


def guardar(
    db: Session,
    subida: UploadFile,
    usuario: Usuario | None,
    *,
    tipos: tuple[str, ...] | None = None,
) -> Archivo:
    """Escribe la subida en el almacén y devuelve su fila, sin confirmar.

    `tipos` restringe lo que se acepta (por defecto, imágenes y PDF): un logo no
    puede ser un PDF.
    """
    limite = settings.archivo_max_mb * 1024 * 1024
    raiz = Path(settings.almacen_dir)
    raiz.mkdir(parents=True, exist_ok=True)

    resumen = hashlib.sha256()
    peso = 0
    mime: str | None = None

    # Se escribe a un temporal del mismo volumen y se renombra al final: nunca
    # queda un archivo a medias bajo su nombre definitivo.
    descriptor, temporal = tempfile.mkstemp(dir=raiz, prefix="subida-")
    try:
        with os.fdopen(descriptor, "wb") as salida:
            while trozo := subida.file.read(TROZO):
                if peso == 0:
                    mime = tipo_de(trozo[:16])
                    if mime is None or (tipos is not None and mime not in tipos):
                        raise HTTPException(
                            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            "Sólo se admiten imágenes (JPG, PNG, WebP)"
                            if tipos == IMAGENES
                            else "Sólo se admiten imágenes (JPG, PNG, WebP) y PDF",
                        )
                peso += len(trozo)
                if peso > limite:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        f"El archivo supera los {settings.archivo_max_mb} MB",
                    )
                resumen.update(trozo)
                salida.write(trozo)

        if peso == 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El archivo está vacío")

        sha256 = resumen.hexdigest()
        destino = ruta(sha256)
        destino.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporal, destino)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise

    archivo = Archivo(
        sha256=sha256,
        nombre_original=Path(subida.filename or "archivo").name[:200],
        mime=mime,
        bytes=peso,
        subido_por=usuario.id if usuario else None,
    )
    db.add(archivo)
    db.flush()
    return archivo


def descartar(db: Session, archivo: Archivo) -> None:
    """Borra la fila, y los bytes si ninguna otra fila los comparte."""
    sha256 = archivo.sha256
    db.delete(archivo)
    db.flush()
    quedan = db.scalar(select(func.count()).select_from(Archivo).where(Archivo.sha256 == sha256))
    if not quedan:
        ruta(sha256).unlink(missing_ok=True)
