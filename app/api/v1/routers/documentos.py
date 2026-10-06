"""Documentos del paciente: plantillas, emisión, firma y recetas."""

from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import BD, UsuarioAuth, requiere_rol
from app.core.security import MINUTOS_ENLACE_FIRMA, create_token, decode_token
from app.models.clinico import Consulta
from app.models.documento import (
    DocumentoEmitido,
    Firma,
    PlantillaDocumento,
    Prescripcion,
    PrescripcionItem,
)
from app.models.enums import RolUsuario
from app.models.organizacion import Doctor, Sede, Usuario
from app.models.paciente import Paciente
from app.models.plan import PlanTratamiento
from app.schemas.documento import (
    Borrador,
    DocumentoAnular,
    DocumentoCrear,
    DocumentoLeer,
    DocumentoParaFirmar,
    DocumentosDelPaciente,
    EnlaceFirma,
    FirmaCrear,
    PlantillaActualizar,
    PlantillaEscribir,
    PlantillaLeer,
    RecetaCrear,
    RecetaLeer,
)
from app.services import documentos as servicio
from app.services.catalogo import codigo_desde_nombre

router = APIRouter(tags=["documentos"])

# Emite quien atiende o quien está en el mostrador; receta sólo quien atiende.
PuedeEmitir = Annotated[
    Usuario,
    Depends(requiere_rol(RolUsuario.DOCTOR, RolUsuario.ASISTENTE, RolUsuario.RECEPCION)),
]
PuedeRecetar = Annotated[Usuario, Depends(requiere_rol(RolUsuario.DOCTOR))]
SoloAdmin = Annotated[Usuario, Depends(requiere_rol())]

NO_PROCESABLE = status.HTTP_422_UNPROCESSABLE_ENTITY


def _paciente(db: Session, paciente_id: int) -> Paciente:
    paciente = db.get(Paciente, paciente_id)
    if paciente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El paciente no existe")
    return paciente


def _documento(db: Session, documento_id: int) -> DocumentoEmitido:
    documento = db.scalar(
        select(DocumentoEmitido)
        .where(DocumentoEmitido.id == documento_id)
        .options(selectinload(DocumentoEmitido.firmas))
    )
    if documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El documento no existe")
    return documento


def _del_paciente(db: Session, modelo: type, objeto_id: int | None, paciente_id: int, campo: str):
    """Una consulta o un plan referenciados deben ser de ese mismo paciente."""
    if objeto_id is None:
        return None
    objeto = db.get(modelo, objeto_id)
    if objeto is None or objeto.paciente_id != paciente_id:
        raise HTTPException(NO_PROCESABLE, f"{campo}: no es de este paciente")
    return objeto


# --- Plantillas ----------------------------------------------------------------


@router.get("/plantillas", response_model=list[PlantillaLeer])
def listar_plantillas(
    db: BD, _: UsuarioAuth, incluir_inactivas: bool = False
) -> list[PlantillaDocumento]:
    consulta = select(PlantillaDocumento).order_by(
        PlantillaDocumento.tipo, PlantillaDocumento.titulo
    )
    if not incluir_inactivas:
        consulta = consulta.where(PlantillaDocumento.activo)
    return list(db.scalars(consulta))


@router.post("/plantillas", response_model=PlantillaLeer, status_code=status.HTTP_201_CREATED)
def crear_plantilla(datos: PlantillaEscribir, db: BD, _: SoloAdmin) -> PlantillaDocumento:
    servicio.validar_plantilla(datos.cuerpo)
    plantilla = PlantillaDocumento(
        **datos.model_dump(),
        codigo=codigo_desde_nombre(db, PlantillaDocumento, datos.titulo),
        activo=True,
    )
    db.add(plantilla)
    db.commit()
    db.refresh(plantilla)
    return plantilla


@router.patch("/plantillas/{plantilla_id}", response_model=PlantillaLeer)
def actualizar_plantilla(
    plantilla_id: int, datos: PlantillaActualizar, db: BD, _: SoloAdmin
) -> PlantillaDocumento:
    """Cambiar una plantilla no toca lo ya emitido: cada documento guarda su texto final."""
    plantilla = db.get(PlantillaDocumento, plantilla_id)
    if plantilla is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La plantilla no existe")

    cambios = {k: v for k, v in datos.model_dump(exclude_unset=True).items() if v is not None}
    if "cuerpo" in cambios:
        servicio.validar_plantilla(cambios["cuerpo"])
    for campo, valor in cambios.items():
        setattr(plantilla, campo, valor)

    db.commit()
    db.refresh(plantilla)
    return plantilla


# --- Documentos de un paciente -------------------------------------------------


@router.get("/pacientes/{paciente_id}/documentos", response_model=DocumentosDelPaciente)
def documentos_del_paciente(paciente_id: int, db: BD, _: UsuarioAuth) -> DocumentosDelPaciente:
    _paciente(db, paciente_id)

    emitidos = db.scalars(
        select(DocumentoEmitido)
        .where(DocumentoEmitido.paciente_id == paciente_id)
        .options(selectinload(DocumentoEmitido.firmas))
        .order_by(DocumentoEmitido.emitido_en.desc())
    ).all()
    recetas = db.scalars(
        select(Prescripcion)
        .where(Prescripcion.paciente_id == paciente_id)
        .options(selectinload(Prescripcion.items))
        .order_by(Prescripcion.fecha.desc(), Prescripcion.id.desc())
    ).all()

    return DocumentosDelPaciente(
        documentos=[DocumentoLeer.model_validate(d) for d in emitidos],
        recetas=[RecetaLeer.model_validate(r) for r in recetas],
        datos_personales_firmados=any(
            d.tipo == "consentimiento_datos" and d.anulado_en is None and d.firmas for d in emitidos
        ),
    )


@router.get("/pacientes/{paciente_id}/documentos/borrador", response_model=Borrador)
def borrador(
    paciente_id: int,
    plantilla_id: int,
    db: BD,
    _: UsuarioAuth,
    consulta_id: int | None = None,
    plan_id: int | None = None,
) -> Borrador:
    """La plantilla combinada con los datos del paciente. No guarda nada: es para revisar."""
    paciente = _paciente(db, paciente_id)
    plantilla = db.get(PlantillaDocumento, plantilla_id)
    if plantilla is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La plantilla no existe")

    datos = servicio.contexto(
        db,
        paciente,
        consulta=_del_paciente(db, Consulta, consulta_id, paciente_id, "consulta_id"),
        plan=_del_paciente(db, PlanTratamiento, plan_id, paciente_id, "plan_id"),
    )
    return Borrador(
        plantilla_id=plantilla.id,
        tipo=plantilla.tipo,
        titulo=plantilla.titulo,
        cuerpo=servicio.combinar(plantilla.cuerpo, datos),
        requiere_firma=plantilla.requiere_firma,
    )


@router.post(
    "/pacientes/{paciente_id}/documentos",
    response_model=DocumentoLeer,
    status_code=status.HTTP_201_CREATED,
)
def emitir(
    paciente_id: int, datos: DocumentoCrear, db: BD, usuario: PuedeEmitir
) -> DocumentoEmitido:
    """Guarda el texto final. A partir de aquí el documento no cambia."""
    _paciente(db, paciente_id)
    _del_paciente(db, Consulta, datos.consulta_id, paciente_id, "consulta_id")
    _del_paciente(db, PlanTratamiento, datos.plan_id, paciente_id, "plan_id")
    if datos.plantilla_id is not None and db.get(PlantillaDocumento, datos.plantilla_id) is None:
        raise HTTPException(NO_PROCESABLE, "plantilla_id: la plantilla no existe")
    if datos.doctor_id is not None and db.get(Doctor, datos.doctor_id) is None:
        raise HTTPException(NO_PROCESABLE, "doctor_id: el doctor no existe")

    cuerpo = datos.cuerpo.strip()
    documento = DocumentoEmitido(
        paciente_id=paciente_id,
        **datos.model_dump(exclude={"cuerpo", "doctor_id"}),
        cuerpo=cuerpo,
        doctor_id=datos.doctor_id or usuario.doctor_id,
        sha256=servicio.sha256(cuerpo),
        emitido_por=usuario.id,
    )
    db.add(documento)
    db.commit()
    return _documento(db, documento.id)


@router.get("/documentos/{documento_id}", response_model=DocumentoLeer)
def obtener_documento(documento_id: int, db: BD, _: UsuarioAuth) -> DocumentoEmitido:
    return _documento(db, documento_id)


@router.post("/documentos/{documento_id}/anular", response_model=DocumentoLeer)
def anular(documento_id: int, datos: DocumentoAnular, db: BD, _: PuedeEmitir) -> DocumentoEmitido:
    documento = _documento(db, documento_id)
    if documento.anulado_en is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "El documento ya estaba anulado")
    documento.anulado_en = datetime.now(UTC)
    documento.motivo_anulacion = datos.motivo.strip()
    db.commit()
    return _documento(db, documento_id)


# --- Firma ---------------------------------------------------------------------


@router.post("/documentos/{documento_id}/enlace-firma", response_model=EnlaceFirma)
def enlace_de_firma(documento_id: int, db: BD, _: PuedeEmitir) -> EnlaceFirma:
    """Un enlace que sirve sólo para firmar este documento, y caduca.

    Se abre en la tableta del consultorio o en el teléfono del paciente, sin
    sesión: quien firma no entra a la aplicación.
    """
    documento = _documento(db, documento_id)
    if documento.anulado_en is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Un documento anulado no se firma")
    return EnlaceFirma(token=create_token(str(documento.id), "firma"), minutos=MINUTOS_ENLACE_FIRMA)


def _por_token(db: Session, token: str) -> DocumentoEmitido:
    payload = decode_token(token, "firma")
    if payload is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "El enlace de firma no es válido o ya caducó"
        )
    documento = _documento(db, int(payload["sub"]))
    if documento.anulado_en is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "El documento fue anulado")
    return documento


@router.get("/firma/{token}", response_model=DocumentoParaFirmar)
def documento_para_firmar(token: str, db: BD) -> DocumentoParaFirmar:
    """Sin sesión. Devuelve sólo el documento: nada más del expediente."""
    documento = _por_token(db, token)
    paciente = db.get(Paciente, documento.paciente_id)
    clinica = db.scalar(select(Sede).where(Sede.activo).order_by(Sede.id))
    return DocumentoParaFirmar(
        titulo=documento.titulo,
        cuerpo=documento.cuerpo,
        paciente_nombre=paciente.nombre_completo,
        clinica_nombre=clinica.nombre if clinica else None,
        ya_firmado=bool(documento.firmas),
    )


def _ip_de(request: Request) -> str | None:
    """Dirección de quien firma. Detrás de nginx llega en X-Forwarded-For."""
    candidata = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
        request.client.host if request.client else ""
    )
    try:
        return str(ip_address(candidata))
    except ValueError:
        return None


@router.post("/firma/{token}", status_code=status.HTTP_204_NO_CONTENT)
def firmar(token: str, datos: FirmaCrear, request: Request, db: BD) -> None:
    documento = _por_token(db, token)
    if documento.firmas:
        raise HTTPException(status.HTTP_409_CONFLICT, "El documento ya está firmado")
    if sum(len(trazo) for trazo in datos.trazo) < 8:
        raise HTTPException(NO_PROCESABLE, "trazo: la firma está vacía o es demasiado corta")

    documento.firmas.append(
        Firma(
            firmante_nombre=datos.firmante_nombre.strip(),
            firmante_rol=datos.firmante_rol,
            firmante_documento=(datos.firmante_documento or "").strip() or None,
            trazo=[[list(punto) for punto in trazo] for trazo in datos.trazo],
            # Lo que se firma es este texto exacto.
            hash_documento=documento.sha256,
            dispositivo=(request.headers.get("user-agent") or "")[:300] or None,
            ip=_ip_de(request),
        )
    )
    db.commit()


# --- Recetas -------------------------------------------------------------------


@router.post(
    "/pacientes/{paciente_id}/recetas",
    response_model=RecetaLeer,
    status_code=status.HTTP_201_CREATED,
)
def recetar(paciente_id: int, datos: RecetaCrear, db: BD, _: PuedeRecetar) -> Prescripcion:
    _paciente(db, paciente_id)
    _del_paciente(db, Consulta, datos.consulta_id, paciente_id, "consulta_id")
    if db.get(Doctor, datos.doctor_id) is None:
        raise HTTPException(NO_PROCESABLE, "doctor_id: el doctor no existe")

    # Recetar contra una alergia registrada exige confirmarlo: no pasa por descuido.
    choques = servicio.choques_con_alergias(
        db, paciente_id, [item.medicamento for item in datos.items]
    )
    if choques and not datos.confirmar_alergias:
        raise HTTPException(status.HTTP_409_CONFLICT, " · ".join(choques))

    receta = Prescripcion(
        paciente_id=paciente_id,
        doctor_id=datos.doctor_id,
        consulta_id=datos.consulta_id,
        indicaciones=(datos.indicaciones or "").strip() or None,
        items=[PrescripcionItem(**item.model_dump()) for item in datos.items],
    )
    db.add(receta)
    db.commit()
    db.refresh(receta)
    return receta
