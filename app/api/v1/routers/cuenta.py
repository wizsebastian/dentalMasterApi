"""Cuenta del paciente, recibos, cuentas por cobrar y caja."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.deps import BD, UsuarioAuth, requiere_rol
from app.core.tiempo import hoy
from app.models.cuenta import Pago
from app.models.enums import RolUsuario
from app.models.organizacion import Usuario
from app.models.paciente import Paciente
from app.schemas.cuenta import (
    Caja,
    ConsultaConSaldo,
    CuentaPorCobrar,
    CuentasPorCobrar,
    EstadoDeCuenta,
    PagoActualizar,
    PagoAnular,
    PagoConPaciente,
    PagoCrear,
    PagoLeer,
    Recibo,
    TotalMetodo,
    TramoAntiguedad,
)
from app.services import cuenta
from app.services.busqueda import digitos_de

router = APIRouter(tags=["cuenta y caja"])

PuedeCobrar = Annotated[
    Usuario,
    Depends(
        requiere_rol(
            RolUsuario.RECEPCION, RolUsuario.FACTURACION, RolUsuario.DOCTOR, RolUsuario.ASISTENTE
        )
    ),
]
# Anular toca dinero ya recibido: sólo quien lleva la caja.
PuedeAnular = Annotated[Usuario, Depends(requiere_rol(RolUsuario.FACTURACION))]

CERO = Decimal(0)


def _pago(db: Session, pago_id: int) -> Pago:
    pago = db.scalar(
        select(Pago).where(Pago.id == pago_id).options(selectinload(Pago.aplicaciones))
    )
    if pago is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El pago no existe")
    return pago


def _leer(pago: Pago) -> PagoLeer:
    return PagoLeer.model_validate(pago).model_copy(
        update={"sin_aplicar": cuenta.sin_aplicar(pago)}
    )


def _con_paciente(db: Session, pago: Pago) -> PagoConPaciente:
    paciente = db.get(Paciente, pago.paciente_id)
    cajero = db.get(Usuario, pago.recibido_por) if pago.recibido_por else None
    return PagoConPaciente(
        **_leer(pago).model_dump(),
        paciente_nombre=paciente.nombre_completo,
        paciente_documento=paciente.documento,
        paciente_telefono=paciente.celular or paciente.telefono,
        recibido_por_email=cajero.email if cajero else None,
    )


_BALANCE = text(
    "SELECT cargos, pagado, credito_sin_aplicar, balance FROM v_estado_cuenta "
    "WHERE paciente_id = :pid"
)

_PENDIENTES = text(
    "SELECT sc.consulta_id, sc.fecha, sc.total, sc.aplicado, sc.saldo, "
    "       COALESCE((SELECT string_agg(s.nombre, ', ' ORDER BY pr.id) "
    "                   FROM procedimiento pr JOIN servicio s ON s.id = pr.servicio_id "
    "                  WHERE pr.consulta_id = sc.consulta_id), 'Consulta') AS descripcion "
    "FROM v_saldo_consulta sc WHERE sc.paciente_id = :pid AND sc.saldo > 0 "
    "ORDER BY sc.fecha, sc.consulta_id"
)


# --- Cuenta de un paciente -----------------------------------------------------


@router.get("/pacientes/{paciente_id}/cuenta", response_model=EstadoDeCuenta)
def estado_de_cuenta(paciente_id: int, db: BD, _: UsuarioAuth) -> EstadoDeCuenta:
    if db.get(Paciente, paciente_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El paciente no existe")

    balance = db.execute(_BALANCE, {"pid": paciente_id}).mappings().one()
    pagos = db.scalars(
        select(Pago)
        .where(Pago.paciente_id == paciente_id)
        .options(selectinload(Pago.aplicaciones))
        .order_by(Pago.fecha.desc(), Pago.id.desc())
    ).all()

    return EstadoDeCuenta(
        paciente_id=paciente_id,
        **balance,
        pagos=[_leer(p) for p in pagos],
        pendientes=[
            ConsultaConSaldo(**fila)
            for fila in db.execute(_PENDIENTES, {"pid": paciente_id}).mappings()
        ],
    )


@router.post(
    "/pacientes/{paciente_id}/pagos", response_model=PagoLeer, status_code=status.HTTP_201_CREATED
)
def registrar_pago(paciente_id: int, datos: PagoCrear, db: BD, usuario: PuedeCobrar) -> PagoLeer:
    """Registra un pago y lo imputa: a la consulta indicada y luego a las más
    antiguas con saldo. Lo que sobre queda como anticipo del paciente."""
    pago = cuenta.registrar_pago(db, paciente_id, **datos.model_dump(), usuario=usuario)
    db.commit()
    return _leer(_pago(db, pago.id))


# --- Pagos ---------------------------------------------------------------------


@router.get("/pagos/{pago_id}", response_model=Recibo)
def recibo(pago_id: int, db: BD, _: UsuarioAuth) -> Recibo:
    """El pago con lo que el recibo impreso necesita."""
    pago = _pago(db, pago_id)
    balance = db.execute(_BALANCE, {"pid": pago.paciente_id}).mappings().one()
    return Recibo(**_con_paciente(db, pago).model_dump(), balance_despues=balance["balance"])


@router.patch("/pagos/{pago_id}", response_model=PagoLeer)
def actualizar_pago(pago_id: int, datos: PagoActualizar, db: BD, _: PuedeCobrar) -> PagoLeer:
    pago = _pago(db, pago_id)
    if pago.anulado_en is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Un pago anulado no se modifica")

    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("metodo"):
        pago.metodo = cambios["metodo"]
    for campo in ("concepto", "referencia"):
        if campo in cambios:
            setattr(pago, campo, (cambios[campo] or "").strip() or None)

    db.commit()
    return _leer(_pago(db, pago_id))


@router.post("/pagos/{pago_id}/anular", response_model=PagoLeer)
def anular_pago(pago_id: int, datos: PagoAnular, db: BD, usuario: PuedeAnular) -> PagoLeer:
    pago = _pago(db, pago_id)
    cuenta.anular_pago(db, pago, datos.motivo, usuario)
    db.commit()
    return _leer(_pago(db, pago_id))


# --- Cuentas por cobrar y caja -------------------------------------------------

_POR_COBRAR = text(
    "SELECT p.id AS paciente_id, p.nombres || ' ' || p.apellidos AS paciente_nombre, "
    "       p.codigo AS paciente_codigo, COALESCE(p.celular, p.telefono) AS paciente_telefono, "
    "       ec.cargos, ec.pagado, ec.balance, "
    "       COALESCE(sc.consultas, 0) AS consultas, sc.desde, "
    "       (CAST(:hoy AS DATE) - (sc.desde AT TIME ZONE :zona)::date) AS dias "
    "FROM v_estado_cuenta ec "
    "JOIN paciente p ON p.id = ec.paciente_id "
    "LEFT JOIN (SELECT paciente_id, count(*) AS consultas, MIN(fecha) AS desde "
    "             FROM v_saldo_consulta WHERE saldo > 0 GROUP BY paciente_id) sc "
    "       ON sc.paciente_id = p.id "
    "WHERE ec.balance > 0 "
    "  AND (CAST(:buscar AS TEXT) IS NULL "
    "       OR unaccent(p.nombres || ' ' || p.apellidos) ILIKE unaccent(:patron) "
    "       OR p.codigo ILIKE :patron "
    "       OR regexp_replace(COALESCE(p.celular, p.telefono, ''), '\\D', '', 'g') "
    "          LIKE :digitos) "
    "ORDER BY sc.desde NULLS LAST, p.apellidos"
)

# Tramos de antigüedad de la deuda, por la consulta con saldo más antigua.
_TRAMOS = (("0 a 30 días", 0, 30), ("31 a 60 días", 31, 60), ("61 a 90 días", 61, 90))


@router.get("/cuentas-por-cobrar", response_model=CuentasPorCobrar)
def cuentas_por_cobrar(
    db: BD, _: PuedeCobrar, buscar: str | None = Query(default=None)
) -> CuentasPorCobrar:
    """Pacientes con saldo, del que debe desde hace más tiempo al más reciente."""
    buscar = (buscar or "").strip() or None
    items = [
        CuentaPorCobrar(**fila)
        for fila in db.execute(
            _POR_COBRAR,
            {
                "buscar": buscar,
                "patron": f"%{buscar}%" if buscar else None,
                # Un teléfono se busca por sus dígitos; sin ellos, no encuentra nada.
                "digitos": f"%{digitos_de(buscar)}%"
                if buscar and len(digitos_de(buscar)) >= 4
                else "%sin-digitos%",
                "hoy": hoy(),
                "zona": settings.zona_horaria,
            },
        ).mappings()
    ]

    tramos = [
        TramoAntiguedad(
            etiqueta=etiqueta,
            pacientes=sum(1 for i in items if i.dias is not None and minimo <= i.dias <= maximo),
            balance=sum(
                (i.balance for i in items if i.dias is not None and minimo <= i.dias <= maximo),
                CERO,
            ),
        )
        for etiqueta, minimo, maximo in _TRAMOS
    ]
    viejos = [i for i in items if i.dias is not None and i.dias > 90]
    tramos.append(
        TramoAntiguedad(
            etiqueta="Más de 90 días",
            pacientes=len(viejos),
            balance=sum((i.balance for i in viejos), CERO),
        )
    )

    return CuentasPorCobrar(
        total=sum((i.balance for i in items), CERO),
        pacientes=len(items),
        antiguedad=tramos,
        items=items,
    )


@router.get("/caja", response_model=Caja)
def caja(
    db: BD,
    _: PuedeCobrar,
    desde: Annotated[date | None, Query(description="Por defecto, hoy")] = None,
    hasta: Annotated[date | None, Query(description="Incluido. Por defecto, igual a desde")] = None,
) -> Caja:
    """Lo cobrado en un tramo de fechas, por método: el cierre de caja."""
    desde = desde or hoy()
    hasta = hasta or desde
    if hasta < desde:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "hasta: anterior a desde")

    pagos = db.scalars(
        select(Pago)
        .where(Pago.fecha >= desde, Pago.fecha <= hasta)
        .options(selectinload(Pago.aplicaciones))
        .order_by(Pago.numero_recibo.desc())
    ).all()
    vivos = [p for p in pagos if p.anulado_en is None]

    por_metodo: dict[str, list[Pago]] = {}
    for pago in vivos:
        por_metodo.setdefault(pago.metodo, []).append(pago)

    return Caja(
        desde=desde,
        hasta=hasta,
        total=sum((p.monto for p in vivos), CERO),
        anulados=len(pagos) - len(vivos),
        por_metodo=[
            TotalMetodo(metodo=metodo, pagos=len(lista), monto=sum((p.monto for p in lista), CERO))
            for metodo, lista in sorted(por_metodo.items())
        ],
        pagos=[_con_paciente(db, p) for p in pagos],
    )
