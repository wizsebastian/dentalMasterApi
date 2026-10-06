"""Archivos: fotos de consulta, exámenes y comprobantes."""

from datetime import date
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.core.deps import BD, UsuarioAuth, requiere_rol
from app.models.archivo import Archivo, DocumentoClinico
from app.models.catalogo import Diente
from app.models.clinico import Consulta
from app.models.cuenta import Pago
from app.models.enums import RolUsuario
from app.models.inventario import Gasto
from app.models.organizacion import Usuario
from app.models.paciente import Paciente
from app.schemas.archivo import (
    ArchivoClinicoActualizar,
    ArchivoClinicoLeer,
    ArchivoLeer,
    TipoArchivo,
)
from app.services import almacen

router = APIRouter(tags=["archivos"])

PuedeSubir = Annotated[
    Usuario,
    Depends(requiere_rol(RolUsuario.DOCTOR, RolUsuario.ASISTENTE, RolUsuario.RECEPCION)),
]
# Quitar un examen del expediente es una decisión clínica.
PuedeQuitar = Annotated[Usuario, Depends(requiere_rol(RolUsuario.DOCTOR))]
PuedeCobrar = Annotated[
    Usuario,
    Depends(
        requiere_rol(
            RolUsuario.RECEPCION, RolUsuario.FACTURACION, RolUsuario.DOCTOR, RolUsuario.ASISTENTE
        )
    ),
]
PuedeGastar = Annotated[Usuario, Depends(requiere_rol(RolUsuario.FACTURACION))]


def _documento(db: BD, documento_id: int) -> DocumentoClinico:
    documento = db.get(DocumentoClinico, documento_id)
    if documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El archivo no existe")
    return documento


def _validar_pieza(db: BD, codigo_fdi: int | None) -> None:
    if codigo_fdi is not None and db.get(Diente, codigo_fdi) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La pieza no existe")


# --- El contenido --------------------------------------------------------------


@router.get("/archivos/{archivo_id}", response_class=FileResponse)
def descargar(archivo_id: int, db: BD, _: UsuarioAuth) -> FileResponse:
    """Los bytes. Exige sesión: la interfaz los pide con su token y los muestra
    desde memoria, de modo que ninguna URL de un examen sirve fuera de ella."""
    archivo = db.get(Archivo, archivo_id)
    if archivo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El archivo no existe")
    ruta = almacen.ruta(archivo.sha256)
    if not ruta.is_file():
        raise HTTPException(status.HTTP_410_GONE, "El archivo ya no está en el almacén")
    return FileResponse(
        ruta,
        media_type=archivo.mime,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(archivo.nombre_original)}",
            "X-Content-Type-Options": "nosniff",
            # El contenido de un id no cambia nunca.
            "Cache-Control": "private, max-age=86400, immutable",
        },
    )


# --- Fotos y exámenes del paciente ---------------------------------------------


@router.get("/pacientes/{paciente_id}/archivos", response_model=list[ArchivoClinicoLeer])
def listar(
    paciente_id: int, db: BD, _: UsuarioAuth, consulta_id: int | None = None
) -> list[DocumentoClinico]:
    if db.get(Paciente, paciente_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El paciente no existe")
    consulta = select(DocumentoClinico).where(DocumentoClinico.paciente_id == paciente_id)
    if consulta_id is not None:
        consulta = consulta.where(DocumentoClinico.consulta_id == consulta_id)
    return list(
        db.scalars(
            consulta.order_by(
                DocumentoClinico.tomado_en.desc().nulls_last(), DocumentoClinico.id.desc()
            )
        )
    )


@router.post(
    "/pacientes/{paciente_id}/archivos",
    response_model=ArchivoClinicoLeer,
    status_code=status.HTTP_201_CREATED,
)
def subir(
    paciente_id: int,
    db: BD,
    usuario: PuedeSubir,
    archivo: Annotated[UploadFile, File()],
    tipo: Annotated[TipoArchivo, Form()] = "foto",
    titulo: Annotated[str | None, Form(max_length=160)] = None,
    consulta_id: Annotated[int | None, Form()] = None,
    codigo_fdi: Annotated[int | None, Form()] = None,
    tomado_en: Annotated[date | None, Form()] = None,
) -> DocumentoClinico:
    if db.get(Paciente, paciente_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El paciente no existe")
    if consulta_id is not None:
        consulta = db.get(Consulta, consulta_id)
        if consulta is None or consulta.paciente_id != paciente_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "La consulta no es de este paciente"
            )
    _validar_pieza(db, codigo_fdi)

    guardado = almacen.guardar(db, archivo, usuario)
    documento = DocumentoClinico(
        paciente_id=paciente_id,
        consulta_id=consulta_id,
        tipo=tipo,
        titulo=(titulo or "").strip() or None,
        codigo_fdi=codigo_fdi,
        tomado_en=tomado_en,
        archivo_id=guardado.id,
        mime=guardado.mime,
    )
    db.add(documento)
    db.commit()
    db.refresh(documento)
    return documento


@router.patch("/archivos-clinicos/{documento_id}", response_model=ArchivoClinicoLeer)
def actualizar(
    documento_id: int, datos: ArchivoClinicoActualizar, db: BD, _: PuedeSubir
) -> DocumentoClinico:
    documento = _documento(db, documento_id)
    cambios = datos.model_dump(exclude_unset=True)
    if "codigo_fdi" in cambios:
        _validar_pieza(db, cambios["codigo_fdi"])
    if cambios.get("tipo", "") is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El tipo es obligatorio")
    for campo, valor in cambios.items():
        setattr(documento, campo, valor)
    db.commit()
    db.refresh(documento)
    return documento


@router.delete("/archivos-clinicos/{documento_id}", status_code=status.HTTP_204_NO_CONTENT)
def quitar(documento_id: int, db: BD, _: PuedeQuitar) -> Response:
    documento = _documento(db, documento_id)
    archivo = documento.archivo
    db.delete(documento)
    db.flush()
    if archivo is not None:
        almacen.descartar(db, archivo)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Comprobantes de pagos y gastos --------------------------------------------


def _adjuntar(db: BD, fila: Pago | Gasto, subida: UploadFile, usuario: Usuario) -> Archivo:
    anterior = db.get(Archivo, fila.comprobante_id) if fila.comprobante_id else None
    guardado = almacen.guardar(db, subida, usuario)
    fila.comprobante_id = guardado.id
    db.flush()
    if anterior is not None:
        almacen.descartar(db, anterior)
    db.commit()
    db.refresh(guardado)
    return guardado


def _desadjuntar(db: BD, fila: Pago | Gasto) -> Response:
    if fila.comprobante_id is not None:
        anterior = db.get(Archivo, fila.comprobante_id)
        fila.comprobante_id = None
        db.flush()
        almacen.descartar(db, anterior)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _pago(db: BD, pago_id: int) -> Pago:
    pago = db.get(Pago, pago_id)
    if pago is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El pago no existe")
    return pago


def _gasto(db: BD, gasto_id: int) -> Gasto:
    gasto = db.get(Gasto, gasto_id)
    if gasto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El gasto no existe")
    return gasto


@router.put("/pagos/{pago_id}/comprobante", response_model=ArchivoLeer)
def adjuntar_a_pago(
    pago_id: int, db: BD, usuario: PuedeCobrar, archivo: Annotated[UploadFile, File()]
) -> Archivo:
    """El voucher o la captura de la transferencia. Sustituye al anterior."""
    return _adjuntar(db, _pago(db, pago_id), archivo, usuario)


@router.delete("/pagos/{pago_id}/comprobante", status_code=status.HTTP_204_NO_CONTENT)
def quitar_de_pago(pago_id: int, db: BD, _: PuedeCobrar) -> Response:
    return _desadjuntar(db, _pago(db, pago_id))


@router.put("/gastos/{gasto_id}/comprobante", response_model=ArchivoLeer)
def adjuntar_a_gasto(
    gasto_id: int, db: BD, usuario: PuedeGastar, archivo: Annotated[UploadFile, File()]
) -> Archivo:
    """La factura del proveedor, en foto o PDF. Sustituye a la anterior."""
    return _adjuntar(db, _gasto(db, gasto_id), archivo, usuario)


@router.delete("/gastos/{gasto_id}/comprobante", status_code=status.HTTP_204_NO_CONTENT)
def quitar_de_gasto(gasto_id: int, db: BD, _: PuedeGastar) -> Response:
    return _desadjuntar(db, _gasto(db, gasto_id))
