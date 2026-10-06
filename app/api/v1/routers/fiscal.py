"""Comprobantes fiscales (NCF) a petición y cierre de caja.

La factura no genera deuda ni recibe pagos: es el comprobante de líneas ya
ejecutadas. La deuda sigue viviendo en la cuenta del paciente.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import BD, UsuarioAuth, requiere_rol
from app.core.tiempo import hoy
from app.models.clinico import Consulta
from app.models.cuenta import CierreCaja, Factura, FacturaItem, Pago, SecuenciaNcf
from app.models.enums import EstadoFactura, EstadoProcedimiento, RolUsuario
from app.models.inventario import Gasto
from app.models.organizacion import Sede, Usuario
from app.models.paciente import Paciente
from app.models.plan import Procedimiento
from app.schemas.fiscal import (
    ETIQUETA_NCF,
    CajaDelDia,
    CierreCrear,
    CierreLeer,
    Emisor,
    FacturaAnular,
    FacturaCrear,
    FacturaImprimible,
    FacturaLeer,
    FacturasDelPaciente,
    LineaFacturable,
    SecuenciaActualizar,
    SecuenciaCrear,
    SecuenciaLeer,
)

router = APIRouter(tags=["comprobantes fiscales y cierre"])

PuedeFacturar = Annotated[
    Usuario, Depends(requiere_rol(RolUsuario.RECEPCION, RolUsuario.FACTURACION))
]
# Anular un NCF se declara a la DGII: sólo quien lleva la contabilidad.
PuedeAnular = Annotated[Usuario, Depends(requiere_rol(RolUsuario.FACTURACION))]
SoloAdmin = Annotated[Usuario, Depends(requiere_rol())]

CERO = Decimal(0)
CONFLICTO = status.HTTP_409_CONFLICT
NO_PROCESABLE = status.HTTP_422_UNPROCESSABLE_ENTITY


# --- Secuencias de NCF ---------------------------------------------------------


@router.get("/secuencias-ncf", response_model=list[SecuenciaLeer])
def listar_secuencias(db: BD, _: PuedeFacturar) -> list[SecuenciaNcf]:
    return list(
        db.scalars(
            select(SecuenciaNcf).order_by(
                SecuenciaNcf.activo.desc(), SecuenciaNcf.tipo, SecuenciaNcf.id.desc()
            )
        )
    )


@router.post("/secuencias-ncf", response_model=SecuenciaLeer, status_code=status.HTTP_201_CREATED)
def crear_secuencia(datos: SecuenciaCrear, db: BD, _: SoloAdmin) -> SecuenciaNcf:
    """Carga un rango nuevo. El que estaba activo para ese tipo queda cerrado."""
    usado = db.scalar(select(func.max(Factura.numero)).where(Factura.numero.like(f"{datos.tipo}%")))
    if usado is not None and int(usado[3:]) >= datos.desde:
        raise HTTPException(
            CONFLICTO, f"desde: ya se emitió el {usado}; el rango nuevo debe empezar después"
        )

    for anterior in db.scalars(
        select(SecuenciaNcf).where(SecuenciaNcf.tipo == datos.tipo, SecuenciaNcf.activo)
    ):
        anterior.activo = False
    db.flush()

    secuencia = SecuenciaNcf(
        tipo=datos.tipo, desde=datos.desde, hasta=datos.hasta, siguiente=datos.desde,
        vence=datos.vence,
    )  # fmt: skip
    db.add(secuencia)
    db.commit()
    db.refresh(secuencia)
    return secuencia


@router.patch("/secuencias-ncf/{secuencia_id}", response_model=SecuenciaLeer)
def actualizar_secuencia(
    secuencia_id: int, datos: SecuenciaActualizar, db: BD, _: SoloAdmin
) -> SecuenciaNcf:
    secuencia = db.get(SecuenciaNcf, secuencia_id)
    if secuencia is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La secuencia no existe")
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("activo") and not secuencia.activo:
        for otra in db.scalars(
            select(SecuenciaNcf).where(SecuenciaNcf.tipo == secuencia.tipo, SecuenciaNcf.activo)
        ):
            otra.activo = False
        db.flush()
    for campo, valor in cambios.items():
        if campo == "activo" and valor is None:
            continue
        setattr(secuencia, campo, valor)
    db.commit()
    db.refresh(secuencia)
    return secuencia


# --- Facturas ------------------------------------------------------------------


def _paciente(db: Session, paciente_id: int) -> Paciente:
    paciente = db.get(Paciente, paciente_id)
    if paciente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El paciente no existe")
    return paciente


def _factura(db: Session, factura_id: int) -> Factura:
    factura = db.scalar(
        select(Factura).where(Factura.id == factura_id).options(selectinload(Factura.items))
    )
    if factura is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La factura no existe")
    return factura


def _ya_facturadas(db: Session, paciente_id: int) -> set[int]:
    """Líneas del paciente que ya están en un comprobante vivo."""
    return set(
        db.scalars(
            select(FacturaItem.procedimiento_id)
            .join(Factura, Factura.id == FacturaItem.factura_id)
            .where(
                Factura.paciente_id == paciente_id,
                Factura.estado != EstadoFactura.ANULADA,
                FacturaItem.procedimiento_id.is_not(None),
            )
        )
    )


def _descripcion(linea: Procedimiento) -> str:
    pieza = f" · pieza {linea.codigo_fdi}" if linea.codigo_fdi else ""
    caras = f" ({linea.superficies})" if linea.superficies else ""
    return f"{linea.servicio.nombre}{pieza}{caras}"


def _lineas_ejecutadas(db: Session, paciente_id: int) -> list[Procedimiento]:
    return list(
        db.scalars(
            select(Procedimiento)
            .where(
                Procedimiento.paciente_id == paciente_id,
                Procedimiento.estado == EstadoProcedimiento.COMPLETADO,
            )
            .order_by(Procedimiento.fecha, Procedimiento.id)
        )
    )


def _imprimible(db: Session, factura: Factura) -> FacturaImprimible:
    paciente = db.get(Paciente, factura.paciente_id)
    sede = db.get(Sede, factura.sede_id) if factura.sede_id else None
    return FacturaImprimible(
        **FacturaLeer.model_validate(factura).model_dump(),
        tipo_etiqueta=ETIQUETA_NCF.get(factura.tipo_ncf or "", "Comprobante fiscal"),
        emisor=Emisor(
            nombre=sede.nombre if sede else "",
            rnc=sede.rnc if sede else None,
            direccion=sede.direccion if sede else None,
            ciudad=sede.ciudad if sede else None,
            telefono=sede.telefono if sede else None,
        ),
        paciente_nombre=paciente.nombre_completo,
        paciente_codigo=paciente.codigo,
        paciente_documento=paciente.documento,
        paciente_direccion=paciente.direccion,
    )


@router.get("/pacientes/{paciente_id}/facturas", response_model=FacturasDelPaciente)
def facturas_del_paciente(paciente_id: int, db: BD, _: UsuarioAuth) -> FacturasDelPaciente:
    """Sus comprobantes y las líneas ejecutadas que aún no tienen ninguno."""
    _paciente(db, paciente_id)
    facturas = db.scalars(
        select(Factura)
        .where(Factura.paciente_id == paciente_id)
        .options(selectinload(Factura.items))
        .order_by(Factura.fecha.desc(), Factura.id.desc())
    ).all()
    facturadas = _ya_facturadas(db, paciente_id)
    return FacturasDelPaciente(
        facturas=[FacturaLeer.model_validate(f) for f in facturas],
        facturables=[
            LineaFacturable(
                procedimiento_id=linea.id,
                consulta_id=linea.consulta_id,
                fecha=linea.fecha,
                descripcion=_descripcion(linea),
                cantidad=linea.cantidad,
                precio=linea.precio,
                descuento_pct=linea.descuento_pct,
                total=linea.total,
            )
            for linea in _lineas_ejecutadas(db, paciente_id)
            if linea.id not in facturadas and linea.total > 0
        ],
    )


@router.post(
    "/pacientes/{paciente_id}/facturas",
    response_model=FacturaImprimible,
    status_code=status.HTTP_201_CREATED,
)
def emitir_factura(
    paciente_id: int, datos: FacturaCrear, db: BD, usuario: PuedeFacturar
) -> FacturaImprimible:
    """Emite un comprobante con el siguiente NCF de la secuencia activa."""
    paciente = _paciente(db, paciente_id)

    lineas = {linea.id: linea for linea in _lineas_ejecutadas(db, paciente_id)}
    facturadas = _ya_facturadas(db, paciente_id)
    for procedimiento_id in datos.procedimiento_ids:
        if procedimiento_id not in lineas:
            raise HTTPException(
                NO_PROCESABLE, "procedimiento_ids: hay una línea que no es de este paciente"
            )
        if procedimiento_id in facturadas:
            raise HTTPException(
                CONFLICTO,
                f"«{lineas[procedimiento_id].servicio.nombre}» ya está en otro comprobante",
            )
    elegidas = [lineas[i] for i in datos.procedimiento_ids]

    # El FOR UPDATE serializa a dos cajas que facturan a la vez: no hay dos
    # comprobantes con el mismo número ni huecos en la secuencia.
    secuencia = db.scalar(
        select(SecuenciaNcf)
        .where(SecuenciaNcf.tipo == datos.tipo_ncf, SecuenciaNcf.activo)
        .with_for_update()
        # Tras el bloqueo se lee la fila tal como está, no la que la sesión recordaba.
        .execution_options(populate_existing=True)
    )
    etiqueta = ETIQUETA_NCF[datos.tipo_ncf].lower()
    if secuencia is None:
        raise HTTPException(
            CONFLICTO,
            f"No hay una secuencia activa de NCF de {etiqueta} ({datos.tipo_ncf}): "
            "cárgala en Configuración",
        )
    if secuencia.vence is not None and secuencia.vence < hoy():
        raise HTTPException(CONFLICTO, f"La secuencia {datos.tipo_ncf} venció: carga la nueva")
    if secuencia.siguiente > secuencia.hasta:
        raise HTTPException(CONFLICTO, f"La secuencia {datos.tipo_ncf} está agotada")

    numero = f"{datos.tipo_ncf}{secuencia.siguiente:08d}"
    secuencia.siguiente += 1

    bruto = sum((linea.cantidad * linea.precio for linea in elegidas), CERO)
    total = sum((linea.total for linea in elegidas), CERO)
    planes = set(
        db.scalars(
            select(Consulta.plan_id).where(Consulta.id.in_({li.consulta_id for li in elegidas}))
        )
    )
    sede = db.scalar(select(Sede).where(Sede.activo).order_by(Sede.id).limit(1))

    factura = Factura(
        paciente_id=paciente_id,
        sede_id=sede.id if sede else None,
        plan_id=planes.pop() if len(planes) == 1 else None,
        numero=numero,
        tipo_ncf=datos.tipo_ncf,
        ncf_vence=secuencia.vence,
        rnc_cliente=datos.rnc_cliente,
        razon_social=(datos.razon_social or "").strip() or paciente.nombre_completo,
        fecha=hoy(),
        subtotal=bruto,
        descuento=bruto - total,
        # Los servicios de salud están exentos de ITBIS.
        impuesto=CERO,
        total=total,
        estado=EstadoFactura.EMITIDA,
        emitida_por=usuario.id,
        items=[
            FacturaItem(
                procedimiento_id=linea.id,
                servicio_id=linea.servicio_id,
                descripcion=_descripcion(linea),
                cantidad=linea.cantidad,
                precio_unit=linea.precio,
                descuento_pct=linea.descuento_pct,
                tasa_impuesto=CERO,
                total=linea.total,
            )
            for linea in elegidas
        ],
    )
    db.add(factura)
    db.commit()
    return _imprimible(db, _factura(db, factura.id))


@router.get("/facturas/{factura_id}", response_model=FacturaImprimible)
def obtener_factura(factura_id: int, db: BD, _: UsuarioAuth) -> FacturaImprimible:
    return _imprimible(db, _factura(db, factura_id))


@router.post("/facturas/{factura_id}/anular", response_model=FacturaLeer)
def anular_factura(factura_id: int, datos: FacturaAnular, db: BD, usuario: PuedeAnular) -> Factura:
    """El número no se reutiliza: queda anulado, y sus líneas vuelven a ser facturables."""
    factura = _factura(db, factura_id)
    if factura.estado == EstadoFactura.ANULADA:
        raise HTTPException(CONFLICTO, f"El comprobante {factura.numero} ya está anulado")
    factura.estado = EstadoFactura.ANULADA
    factura.anulada_en = datetime.now(UTC)
    factura.anulada_por = usuario.id
    factura.motivo_anulacion = datos.motivo.strip()
    db.commit()
    return _factura(db, factura_id)


# --- Cierre de caja ------------------------------------------------------------


def _caja_viva(db: Session, fecha: date) -> tuple[Decimal, dict[str, Decimal], Decimal]:
    """Cobrado, desglose por método y gastos en efectivo de ese día, sin anulados."""
    por_metodo = {
        metodo: monto
        for metodo, monto in db.execute(
            select(Pago.metodo, func.sum(Pago.monto))
            .where(Pago.fecha == fecha, Pago.anulado_en.is_(None))
            .group_by(Pago.metodo)
            .order_by(Pago.metodo)
        )
    }
    gastos = db.scalar(
        select(func.coalesce(func.sum(Gasto.monto), 0)).where(
            Gasto.fecha == fecha, Gasto.anulado_en.is_(None), Gasto.metodo == "efectivo"
        )
    )
    return sum(por_metodo.values(), CERO), por_metodo, gastos or CERO


def _cierre_leer(db: Session, cierre: CierreCaja) -> CierreLeer:
    cajero = db.get(Usuario, cierre.cerrado_por) if cierre.cerrado_por else None
    return CierreLeer.model_validate(cierre).model_copy(
        update={"cerrado_por_email": cajero.email if cajero else None}
    )


@router.get("/caja/dia", response_model=CajaDelDia)
def caja_del_dia(
    db: BD,
    _: PuedeFacturar,
    fecha: Annotated[date | None, Query(description="Por defecto, hoy")] = None,
) -> CajaDelDia:
    fecha = fecha or hoy()
    cobrado, por_metodo, gastos = _caja_viva(db, fecha)
    efectivo = por_metodo.get("efectivo", CERO)
    cierre = db.scalar(select(CierreCaja).where(CierreCaja.fecha == fecha))
    return CajaDelDia(
        fecha=fecha,
        cobrado=cobrado,
        por_metodo=por_metodo,
        efectivo_cobrado=efectivo,
        gastos_efectivo=gastos,
        efectivo_esperado=efectivo - gastos,
        cierre=_cierre_leer(db, cierre) if cierre else None,
        movido_tras_cierre=(cobrado - cierre.cobrado) if cierre else CERO,
    )


@router.get("/caja/cierres", response_model=list[CierreLeer])
def listar_cierres(
    db: BD,
    _: PuedeFacturar,
    limite: Annotated[int, Query(ge=1, le=120)] = 30,
) -> list[CierreLeer]:
    cierres = db.scalars(select(CierreCaja).order_by(CierreCaja.fecha.desc()).limit(limite))
    return [_cierre_leer(db, c) for c in cierres]


@router.post("/caja/cierres", response_model=CierreLeer, status_code=status.HTTP_201_CREATED)
def cerrar_caja(datos: CierreCrear, db: BD, usuario: PuedeFacturar) -> CierreLeer:
    """Guarda la foto del día: lo cobrado por método y el efectivo contado."""
    fecha = datos.fecha or hoy()
    if fecha > hoy():
        raise HTTPException(NO_PROCESABLE, "fecha: no se cierra un día que no ha llegado")
    if db.scalar(select(CierreCaja.id).where(CierreCaja.fecha == fecha)):
        raise HTTPException(CONFLICTO, "La caja de ese día ya está cerrada")

    cobrado, por_metodo, gastos = _caja_viva(db, fecha)
    esperado = por_metodo.get("efectivo", CERO) - gastos
    notas = (datos.notas or "").strip() or None
    if datos.efectivo_contado != esperado and notas is None:
        raise HTTPException(
            NO_PROCESABLE,
            "notas: el efectivo contado no coincide con el esperado; explica la diferencia",
        )

    cierre = CierreCaja(
        fecha=fecha,
        cobrado=cobrado,
        efectivo_esperado=esperado,
        efectivo_contado=datos.efectivo_contado,
        desglose={
            **{metodo: str(monto) for metodo, monto in por_metodo.items()},
            "gastos_efectivo": str(gastos),
        },
        notas=notas,
        cerrado_por=usuario.id,
    )
    db.add(cierre)
    db.commit()
    db.refresh(cierre)
    return _cierre_leer(db, cierre)


@router.delete("/caja/cierres/{cierre_id}", status_code=status.HTTP_204_NO_CONTENT)
def reabrir_caja(cierre_id: int, db: BD, _: SoloAdmin) -> None:
    """Deshace un cierre equivocado. Sólo administración."""
    cierre = db.get(CierreCaja, cierre_id)
    if cierre is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El cierre no existe")
    db.delete(cierre)
    db.commit()
