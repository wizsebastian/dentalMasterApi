"""Gastos, insumos con su kárdex, recetas de servicio e informes."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import BD, UsuarioAuth, requiere_rol
from app.core.tiempo import hoy
from app.models.enums import RolUsuario
from app.models.inventario import (
    CategoriaGasto,
    CategoriaInsumo,
    Gasto,
    Insumo,
    MovimientoInsumo,
    Proveedor,
    ServicioInsumo,
)
from app.models.organizacion import Doctor, Usuario
from app.models.paciente import Paciente
from app.models.servicio import Servicio
from app.schemas.inventario import (
    CostoServicio,
    FilaDoctor,
    FilaUnidad,
    GastoAnular,
    GastoCrear,
    GastoLeer,
    Gastos,
    InsumoActualizar,
    InsumoCrear,
    InsumoLeer,
    Inventario,
    MovimientoCrear,
    MovimientoLeer,
    NombreCrear,
    NombreLeer,
    ProveedorLeer,
    RecetaInsumo,
    RecetaInsumoLeer,
    Resumen,
    TotalPorNombre,
)
from app.services import inventario as servicio
from app.services.busqueda import coincide

router = APIRouter(tags=["gastos, inventario e informes"])

# El dinero que sale y los informes: quien lleva las cuentas.
LlevaCuentas = Annotated[Usuario, Depends(requiere_rol(RolUsuario.FACTURACION))]
# El almacén lo mueve también quien atiende: es quien abre la caja de guantes.
MueveAlmacen = Annotated[
    Usuario,
    Depends(requiere_rol(RolUsuario.FACTURACION, RolUsuario.DOCTOR, RolUsuario.ASISTENTE)),
]
SoloAdmin = Annotated[Usuario, Depends(requiere_rol())]

NO_PROCESABLE = status.HTTP_422_UNPROCESSABLE_ENTITY
CERO = Decimal(0)
TIPOS = {"consultorio": "Consultorio", "doctor": "Doctores", "personal": "Personal"}


def _tramo(desde: date | None, hasta: date | None) -> tuple[date, date]:
    """Por defecto, del primer día del mes a hoy."""
    hasta = hasta or hoy()
    desde = desde or hasta.replace(day=1)
    if hasta < desde:
        raise HTTPException(NO_PROCESABLE, "hasta: anterior a desde")
    return desde, hasta


def _nombre_libre(db: Session, modelo: type, nombre: str) -> None:
    if db.scalar(select(modelo.id).where(func.lower(modelo.nombre) == nombre.strip().lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe «{nombre.strip()}»")


# --- Categorías y proveedores --------------------------------------------------


@router.get("/categorias-gasto", response_model=list[NombreLeer])
def categorias_de_gasto(db: BD, _: UsuarioAuth) -> list[CategoriaGasto]:
    return list(
        db.scalars(
            select(CategoriaGasto).where(CategoriaGasto.activo).order_by(CategoriaGasto.nombre)
        )
    )


@router.post("/categorias-gasto", response_model=NombreLeer, status_code=status.HTTP_201_CREATED)
def crear_categoria_de_gasto(datos: NombreCrear, db: BD, _: LlevaCuentas) -> CategoriaGasto:
    _nombre_libre(db, CategoriaGasto, datos.nombre)
    categoria = CategoriaGasto(nombre=datos.nombre.strip(), activo=True)
    db.add(categoria)
    db.commit()
    db.refresh(categoria)
    return categoria


@router.get("/categorias-insumo", response_model=list[NombreLeer])
def categorias_de_insumo(db: BD, _: UsuarioAuth) -> list[CategoriaInsumo]:
    return list(db.scalars(select(CategoriaInsumo).order_by(CategoriaInsumo.nombre)))


@router.post("/categorias-insumo", response_model=NombreLeer, status_code=status.HTTP_201_CREATED)
def crear_categoria_de_insumo(datos: NombreCrear, db: BD, _: MueveAlmacen) -> CategoriaInsumo:
    _nombre_libre(db, CategoriaInsumo, datos.nombre)
    categoria = CategoriaInsumo(nombre=datos.nombre.strip())
    db.add(categoria)
    db.commit()
    db.refresh(categoria)
    return categoria


@router.get("/proveedores", response_model=list[ProveedorLeer])
def proveedores(db: BD, _: LlevaCuentas) -> list[Proveedor]:
    return list(db.scalars(select(Proveedor).where(Proveedor.activo).order_by(Proveedor.nombre)))


def _proveedor(db: Session, nombre: str | None, rnc: str | None) -> Proveedor | None:
    """Busca al proveedor por nombre (sin mayúsculas) o lo da de alta.

    Es un catálogo y no texto libre para poder detectar un comprobante repetido.
    """
    nombre = (nombre or "").strip()
    rnc = (rnc or "").strip() or None
    if not nombre:
        if rnc:
            raise HTTPException(NO_PROCESABLE, "proveedor: falta el nombre del proveedor")
        return None

    proveedor = db.scalar(select(Proveedor).where(func.lower(Proveedor.nombre) == nombre.lower()))
    if proveedor is None:
        proveedor = Proveedor(nombre=nombre, rnc=rnc, activo=True)
        db.add(proveedor)
        db.flush()
    elif rnc and not proveedor.rnc:
        proveedor.rnc = rnc
    return proveedor


# --- Gastos --------------------------------------------------------------------


@router.get("/gastos", response_model=Gastos)
def listar_gastos(
    db: BD,
    _: LlevaCuentas,
    desde: Annotated[date | None, Query(description="Por defecto, el día 1 del mes")] = None,
    hasta: Annotated[date | None, Query(description="Incluido. Por defecto, hoy")] = None,
    tipo: str | None = None,
    categoria_id: int | None = None,
    doctor_id: int | None = None,
    buscar: str | None = None,
) -> Gastos:
    desde, hasta = _tramo(desde, hasta)
    consulta = select(Gasto).where(Gasto.fecha >= desde, Gasto.fecha <= hasta)
    if tipo:
        consulta = consulta.where(Gasto.tipo == tipo)
    if categoria_id:
        consulta = consulta.where(Gasto.categoria_id == categoria_id)
    if doctor_id:
        consulta = consulta.where(Gasto.doctor_id == doctor_id)
    if buscar and buscar.strip():
        consulta = consulta.outerjoin(Proveedor, Proveedor.id == Gasto.proveedor_id).where(
            or_(
                coincide(Gasto.descripcion, buscar),
                coincide(Gasto.ncf, buscar),
                coincide(Proveedor.nombre, buscar),
            )
        )

    gastos = db.scalars(consulta.order_by(Gasto.fecha.desc(), Gasto.id.desc())).all()
    vivos = [g for g in gastos if g.anulado_en is None]

    def agrupar(clave) -> list[TotalPorNombre]:
        grupos: dict[str, list[Gasto]] = {}
        for gasto in vivos:
            grupos.setdefault(clave(gasto), []).append(gasto)
        return sorted(
            (
                TotalPorNombre(nombre=n, gastos=len(g), monto=sum((x.monto for x in g), CERO))
                for n, g in grupos.items()
            ),
            key=lambda fila: -fila.monto,
        )

    return Gastos(
        desde=desde,
        hasta=hasta,
        total=sum((g.monto for g in vivos), CERO),
        itbis=sum((g.itbis for g in vivos), CERO),
        por_tipo=agrupar(lambda g: TIPOS[g.tipo]),
        por_categoria=agrupar(lambda g: g.categoria.nombre),
        items=[GastoLeer.model_validate(g) for g in gastos],
    )


@router.post("/gastos", response_model=GastoLeer, status_code=status.HTTP_201_CREATED)
def registrar_gasto(datos: GastoCrear, db: BD, usuario: LlevaCuentas) -> Gasto:
    if db.get(CategoriaGasto, datos.categoria_id) is None:
        raise HTTPException(NO_PROCESABLE, "categoria_id: la categoría no existe")
    # El honorario dice de quién es; lo demás no lleva doctor.
    if datos.tipo == "doctor":
        if datos.doctor_id is None or db.get(Doctor, datos.doctor_id) is None:
            raise HTTPException(NO_PROCESABLE, "doctor_id: indica a qué doctor se le paga")
    elif datos.doctor_id is not None:
        raise HTTPException(NO_PROCESABLE, "doctor_id: sólo va en los gastos de tipo doctor")
    if datos.paciente_id is not None and db.get(Paciente, datos.paciente_id) is None:
        raise HTTPException(NO_PROCESABLE, "paciente_id: el paciente no existe")
    if datos.itbis > datos.monto:
        raise HTTPException(NO_PROCESABLE, "itbis: no puede superar al monto")
    if datos.fecha is not None and datos.fecha > hoy():
        raise HTTPException(NO_PROCESABLE, "fecha: un gasto no puede fecharse en el futuro")

    proveedor = _proveedor(db, datos.proveedor, datos.proveedor_rnc)
    if datos.ncf and proveedor is None:
        raise HTTPException(NO_PROCESABLE, "proveedor: un comprobante necesita su proveedor")
    if datos.ncf and db.scalar(
        select(Gasto.id).where(Gasto.proveedor_id == proveedor.id, Gasto.ncf == datos.ncf)
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"El comprobante {datos.ncf} de {proveedor.nombre} ya está registrado",
        )

    gasto = Gasto(
        **datos.model_dump(exclude={"proveedor", "proveedor_rnc", "compras", "fecha"}),
        fecha=datos.fecha or hoy(),
        proveedor_id=proveedor.id if proveedor else None,
        registrado_por=usuario.id,
    )
    db.add(gasto)
    db.flush()

    # Lo comprado entra al kárdex atado a este gasto, y actualiza el último costo.
    for posicion, compra in enumerate(datos.compras, start=1):
        insumo = db.get(Insumo, compra.insumo_id)
        if insumo is None:
            raise HTTPException(NO_PROCESABLE, f"compras {posicion}: el insumo no existe")
        servicio.mover(
            db,
            insumo,
            compra.cantidad,
            "compra",
            usuario_id=usuario.id,
            costo_unit=compra.costo_unit,
            gasto_id=gasto.id,
        )
        insumo.costo = compra.costo_unit

    db.commit()
    db.refresh(gasto)
    return gasto


@router.post("/gastos/{gasto_id}/anular", response_model=GastoLeer)
def anular_gasto(gasto_id: int, datos: GastoAnular, db: BD, usuario: LlevaCuentas) -> Gasto:
    """Como el pago: no se borra. Lo que trajo al almacén sale con un asiento contrario."""
    gasto = db.get(Gasto, gasto_id)
    if gasto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El gasto no existe")
    if gasto.anulado_en is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "El gasto ya estaba anulado")

    for entrada in db.scalars(
        select(MovimientoInsumo).where(MovimientoInsumo.gasto_id == gasto_id)
    ):
        servicio.mover(
            db,
            db.get(Insumo, entrada.insumo_id),
            -entrada.cantidad,
            "devolucion",
            usuario_id=usuario.id,
            gasto_id=gasto_id,
            nota="Compra anulada",
        )
    gasto.anulado_en = datetime.now(UTC)
    gasto.anulado_por = usuario.id
    gasto.motivo_anulacion = datos.motivo.strip()

    db.commit()
    db.refresh(gasto)
    return gasto


# --- Insumos -------------------------------------------------------------------


def _insumo(db: Session, insumo_id: int) -> Insumo:
    insumo = db.get(Insumo, insumo_id)
    if insumo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El insumo no existe")
    return insumo


def _insumo_leer(insumo: Insumo, existencias: dict[int, dict]) -> InsumoLeer:
    dato = existencias.get(insumo.id, {})
    return InsumoLeer.model_validate(insumo).model_copy(
        update={
            "existencia": dato.get("existencia", CERO),
            "valor": dato.get("valor", CERO),
            "bajo_minimo": dato.get("bajo_minimo", False),
        }
    )


@router.get("/insumos", response_model=Inventario)
def inventario(db: BD, _: UsuarioAuth, incluir_inactivos: bool = False) -> Inventario:
    """Un solo catálogo de insumos, con su existencia calculada del kárdex."""
    consulta = select(Insumo).order_by(func.lower(Insumo.nombre))
    if not incluir_inactivos:
        consulta = consulta.where(Insumo.activo)

    existencias = servicio.existencias(db)
    items = [_insumo_leer(i, existencias) for i in db.scalars(consulta)]
    return Inventario(
        insumos=len(items),
        bajo_minimo=sum(1 for i in items if i.bajo_minimo),
        valor=sum((i.valor for i in items if i.controla_stock), CERO),
        items=items,
    )


@router.post("/insumos", response_model=InsumoLeer, status_code=status.HTTP_201_CREATED)
def crear_insumo(datos: InsumoCrear, db: BD, usuario: MueveAlmacen) -> InsumoLeer:
    _nombre_libre(db, Insumo, datos.nombre)
    if datos.categoria_id is not None and db.get(CategoriaInsumo, datos.categoria_id) is None:
        raise HTTPException(NO_PROCESABLE, "categoria_id: la categoría no existe")

    insumo = Insumo(
        **datos.model_dump(exclude={"existencia_inicial", "nombre"}),
        nombre=datos.nombre.strip(),
        activo=True,
    )
    db.add(insumo)
    db.flush()
    servicio.mover(
        db,
        insumo,
        datos.existencia_inicial,
        "inicial",
        usuario_id=usuario.id,
        costo_unit=datos.costo,
    )
    db.commit()
    return _insumo_leer(insumo, servicio.existencias(db))


@router.patch("/insumos/{insumo_id}", response_model=InsumoLeer)
def actualizar_insumo(
    insumo_id: int, datos: InsumoActualizar, db: BD, _: MueveAlmacen
) -> InsumoLeer:
    insumo = _insumo(db, insumo_id)
    cambios = datos.model_dump(exclude_unset=True)

    if cambios.get("nombre") and cambios["nombre"].strip().lower() != insumo.nombre.lower():
        _nombre_libre(db, Insumo, cambios["nombre"])
    if cambios.get("categoria_id") and db.get(CategoriaInsumo, cambios["categoria_id"]) is None:
        raise HTTPException(NO_PROCESABLE, "categoria_id: la categoría no existe")

    anulables = {"categoria_id", "marca", "modelo", "notas"}
    for campo, valor in cambios.items():
        if valor is None and campo not in anulables:
            raise HTTPException(NO_PROCESABLE, f"{campo}: no puede quedar vacío")
        setattr(insumo, campo, valor.strip() if isinstance(valor, str) else valor)

    db.commit()
    return _insumo_leer(insumo, servicio.existencias(db))


@router.get("/insumos/{insumo_id}/movimientos", response_model=list[MovimientoLeer])
def kardex(insumo_id: int, db: BD, _: UsuarioAuth) -> list[MovimientoInsumo]:
    _insumo(db, insumo_id)
    return list(
        db.scalars(
            select(MovimientoInsumo)
            .where(MovimientoInsumo.insumo_id == insumo_id)
            .order_by(MovimientoInsumo.ocurrido_en.desc(), MovimientoInsumo.id.desc())
            .limit(200)
        )
    )


@router.post(
    "/insumos/{insumo_id}/movimientos",
    response_model=InsumoLeer,
    status_code=status.HTTP_201_CREATED,
)
def mover_insumo(
    insumo_id: int, datos: MovimientoCrear, db: BD, usuario: MueveAlmacen
) -> InsumoLeer:
    """Un asiento manual: una compra suelta, una merma o un conteo de estante."""
    insumo = _insumo(db, insumo_id)
    if not insumo.controla_stock:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"«{insumo.nombre}» no lleva existencia: no tiene kárdex"
        )

    if datos.motivo == "conteo":
        # Se dice lo que hay; el asiento es la diferencia con lo que el sistema creía.
        cantidad = datos.cantidad - servicio.existencia_de(db, insumo_id)
    elif datos.motivo == "merma":
        cantidad = -datos.cantidad
    else:
        cantidad = datos.cantidad
    if cantidad == 0 and datos.motivo != "conteo":
        raise HTTPException(NO_PROCESABLE, "cantidad: debe ser mayor que cero")

    servicio.mover(
        db,
        insumo,
        cantidad,
        datos.motivo,
        usuario_id=usuario.id,
        costo_unit=datos.costo_unit,
        nota=(datos.nota or "").strip() or None,
    )
    if datos.motivo == "compra" and datos.costo_unit is not None:
        insumo.costo = datos.costo_unit

    db.commit()
    return _insumo_leer(insumo, servicio.existencias(db))


# --- Receta de insumos de un servicio ------------------------------------------


def _receta(db: Session, servicio_id: int) -> list[RecetaInsumoLeer]:
    return [
        RecetaInsumoLeer(
            insumo_id=r.insumo_id,
            nombre=r.insumo.nombre,
            unidad=r.insumo.unidad,
            cantidad=r.cantidad,
            costo=(r.cantidad * r.insumo.costo).quantize(Decimal("0.01")),
        )
        for r in db.scalars(select(ServicioInsumo).where(ServicioInsumo.servicio_id == servicio_id))
    ]


@router.get("/servicios/{servicio_id}/insumos", response_model=list[RecetaInsumoLeer])
def receta_del_servicio(servicio_id: int, db: BD, _: UsuarioAuth) -> list[RecetaInsumoLeer]:
    if db.get(Servicio, servicio_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El servicio no existe")
    return _receta(db, servicio_id)


@router.put("/servicios/{servicio_id}/insumos", response_model=list[RecetaInsumoLeer])
def guardar_receta(
    servicio_id: int, datos: list[RecetaInsumo], db: BD, _: SoloAdmin
) -> list[RecetaInsumoLeer]:
    """Reemplaza la receta. Es lo que da el costo del servicio y lo que se
    descuenta del almacén cada vez que se ejecuta."""
    if db.get(Servicio, servicio_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El servicio no existe")
    if len({r.insumo_id for r in datos}) != len(datos):
        raise HTTPException(NO_PROCESABLE, "El mismo insumo aparece dos veces")
    for renglon in datos:
        if db.get(Insumo, renglon.insumo_id) is None:
            raise HTTPException(NO_PROCESABLE, f"El insumo {renglon.insumo_id} no existe")

    db.execute(text("DELETE FROM servicio_insumo WHERE servicio_id = :s"), {"s": servicio_id})
    for renglon in datos:
        db.add(ServicioInsumo(servicio_id=servicio_id, **renglon.model_dump()))
    db.commit()
    return _receta(db, servicio_id)


@router.get("/costos-servicio", response_model=list[CostoServicio])
def costos_de_servicio(db: BD, _: LlevaCuentas) -> list[CostoServicio]:
    """Costo en insumos de cada servicio con receta, para ver su margen."""
    return [
        CostoServicio(**fila)
        for fila in db.execute(
            text("SELECT servicio_id, costo_insumos FROM v_costo_servicio")
        ).mappings()
    ]


# --- Informes ------------------------------------------------------------------

_DOCTORES = text(
    "SELECT d.id AS doctor_id, d.nombres || ' ' || d.apellidos AS doctor_nombre, "
    "       COALESCE(d.porcentaje_comision, 0) AS comision_pct, "
    "       COALESCE((SELECT SUM(pr.total) FROM procedimiento pr "
    "                  WHERE pr.doctor_id = d.id AND pr.estado IN ('en_proceso','completado') "
    "                    AND pr.fecha BETWEEN :desde AND :hasta), 0) AS produccion, "
    "       COALESCE((SELECT SUM(a.monto) FROM pago_aplicacion a "
    "                   JOIN pago pg ON pg.id = a.pago_id AND pg.anulado_en IS NULL "
    "                   JOIN consulta c ON c.id = a.consulta_id "
    "                  WHERE c.doctor_id = d.id "
    "                    AND pg.fecha BETWEEN :desde AND :hasta), 0) AS cobrado, "
    "       COALESCE((SELECT SUM(g.monto) FROM gasto g "
    "                  WHERE g.doctor_id = d.id AND g.anulado_en IS NULL "
    "                    AND g.fecha BETWEEN :desde AND :hasta), 0) AS pagado "
    "FROM doctor d WHERE d.activo ORDER BY d.apellidos, d.nombres"
)

_UNIDADES = text(
    "SELECT COALESCE(u.nombre, 'Sin unidad') AS unidad, count(DISTINCT c.id) AS consultas, "
    "       COALESCE(SUM(pr.total), 0) AS produccion "
    "FROM consulta c "
    "LEFT JOIN unidad_dental u ON u.id = c.unidad_id "
    "LEFT JOIN procedimiento pr ON pr.consulta_id = c.id "
    "      AND pr.estado IN ('en_proceso','completado') "
    "WHERE (c.fecha AT TIME ZONE :zona)::date BETWEEN :desde AND :hasta "
    "GROUP BY u.nombre, u.orden ORDER BY u.orden NULLS LAST"
)


@router.get("/informes/resumen", response_model=Resumen)
def resumen(
    db: BD,
    _: LlevaCuentas,
    desde: Annotated[date | None, Query(description="Por defecto, el día 1 del mes")] = None,
    hasta: Annotated[date | None, Query(description="Incluido. Por defecto, hoy")] = None,
) -> Resumen:
    """Ingresos, gastos y neto del tramo, y quién lo produjo.

    La comisión de cada doctor es sobre lo **cobrado** por sus consultas, no
    sobre lo ejecutado: se le liquida lo que efectivamente entró.
    """
    desde, hasta = _tramo(desde, hasta)
    tramo = {"desde": desde, "hasta": hasta}

    def escalar(sql: str) -> Decimal:
        return db.execute(text(sql), tramo).scalar_one()

    ingresos = escalar(
        "SELECT COALESCE(SUM(monto), 0) FROM pago "
        "WHERE anulado_en IS NULL AND fecha BETWEEN :desde AND :hasta"
    )
    gastos = escalar(
        "SELECT COALESCE(SUM(monto), 0) FROM gasto "
        "WHERE anulado_en IS NULL AND fecha BETWEEN :desde AND :hasta"
    )
    produccion = escalar(
        "SELECT COALESCE(SUM(total), 0) FROM procedimiento "
        "WHERE estado IN ('en_proceso','completado') AND fecha BETWEEN :desde AND :hasta"
    )
    por_cobrar = db.execute(
        text("SELECT COALESCE(SUM(balance), 0) FROM v_estado_cuenta WHERE balance > 0")
    ).scalar_one()

    doctores = []
    for fila in db.execute(_DOCTORES, tramo).mappings():
        comision = (fila["cobrado"] * fila["comision_pct"] / 100).quantize(Decimal("0.01"))
        doctores.append(FilaDoctor(**fila, comision=comision))

    return Resumen(
        desde=desde,
        hasta=hasta,
        ingresos=ingresos,
        gastos=gastos,
        neto=ingresos - gastos,
        produccion=produccion,
        por_cobrar=por_cobrar,
        doctores=doctores,
        unidades=[
            FilaUnidad(**fila)
            for fila in db.execute(_UNIDADES, {**tramo, "zona": settings.zona_horaria}).mappings()
        ],
    )
