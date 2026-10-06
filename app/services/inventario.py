"""El kárdex: toda existencia es la suma de sus movimientos."""

from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.inventario import Insumo, MovimientoInsumo, ServicioInsumo
from app.models.plan import Procedimiento

CERO = Decimal(0)

_EXISTENCIAS = text("SELECT insumo_id, existencia, valor, bajo_minimo FROM v_existencia_insumo")


def existencias(db: Session) -> dict[int, dict]:
    return {f["insumo_id"]: dict(f) for f in db.execute(_EXISTENCIAS).mappings()}


def existencia_de(db: Session, insumo_id: int) -> Decimal:
    return db.execute(
        text("SELECT existencia FROM v_existencia_insumo WHERE insumo_id = :id"), {"id": insumo_id}
    ).scalar_one()


def mover(
    db: Session,
    insumo: Insumo,
    cantidad: Decimal,
    motivo: str,
    *,
    usuario_id: int | None = None,
    costo_unit: Decimal | None = None,
    gasto_id: int | None = None,
    procedimiento_id: int | None = None,
    nota: str | None = None,
) -> MovimientoInsumo | None:
    """Añade un asiento. Un insumo que no controla existencia no tiene kárdex."""
    if not insumo.controla_stock or cantidad == 0:
        return None
    movimiento = MovimientoInsumo(
        insumo_id=insumo.id,
        cantidad=cantidad,
        motivo=motivo,
        costo_unit=costo_unit,
        gasto_id=gasto_id,
        procedimiento_id=procedimiento_id,
        nota=nota,
        usuario_id=usuario_id,
    )
    db.add(movimiento)
    return movimiento


def consumir_linea(db: Session, linea: Procedimiento) -> None:
    """Descuenta lo que la receta del servicio dice que gasta esta línea.

    Nunca bloquea el registro clínico: si no hay existencia, queda en negativo y
    lo dirá el próximo conteo.
    """
    receta = db.scalars(
        select(ServicioInsumo).where(ServicioInsumo.servicio_id == linea.servicio_id)
    ).all()
    for renglon in receta:
        mover(
            db,
            renglon.insumo,
            -(renglon.cantidad * linea.cantidad),
            "consumo",
            procedimiento_id=linea.id,
        )
    db.flush()


def devolver_linea(db: Session, linea: Procedimiento) -> None:
    """Deshace el consumo de una línea que se quita o cambia.

    El kárdex no se borra: lo consumido vuelve con un asiento de devolución.
    """
    consumido = db.scalars(
        select(MovimientoInsumo).where(MovimientoInsumo.procedimiento_id == linea.id)
    ).all()
    neto: dict[int, Decimal] = {}
    for movimiento in consumido:
        neto[movimiento.insumo_id] = neto.get(movimiento.insumo_id, CERO) + movimiento.cantidad
    for insumo_id, cantidad in neto.items():
        if cantidad < 0:
            mover(
                db,
                db.get(Insumo, insumo_id),
                -cantidad,
                "devolucion",
                procedimiento_id=linea.id,
                nota="Línea de consulta retirada o modificada",
            )
    db.flush()
