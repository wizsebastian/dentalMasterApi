"""La cuenta del paciente: registrar, aplicar y anular pagos.

El cargo es `procedimiento.total`; el pago es del paciente. `pago_aplicacion`
dice a qué consulta se imputa cada pago, y lo que un pago no tiene aplicado es
crédito a favor. Con eso el saldo por consulta y el balance del paciente salen
de los mismos datos y concilian siempre.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.tiempo import hoy
from app.models.cuenta import Pago, PagoAplicacion
from app.models.organizacion import Usuario
from app.models.paciente import Paciente
from app.services import correlativos

CERO = Decimal(0)

_CON_SALDO = text(
    "SELECT consulta_id, saldo FROM v_saldo_consulta "
    "WHERE paciente_id = :pid AND saldo > 0 ORDER BY fecha, consulta_id"
)


def bloquear_paciente(db: Session, paciente_id: int) -> None:
    """Toma la fila del paciente hasta el fin de la transacción.

    Dos cobros simultáneos al mismo paciente leerían el mismo saldo y lo
    aplicarían dos veces; con el bloqueo se hacen uno detrás de otro.
    """
    # Sólo la columna id: el modelo trae relaciones con LEFT JOIN, y Postgres no
    # admite FOR UPDATE sobre el lado opcional de un join.
    existe = db.scalar(select(Paciente.id).where(Paciente.id == paciente_id).with_for_update())
    if existe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El paciente no existe")


def _saldos(db: Session, paciente_id: int) -> list[tuple[int, Decimal]]:
    """Consultas con saldo, de la más antigua a la más reciente."""
    return [(f.consulta_id, f.saldo) for f in db.execute(_CON_SALDO, {"pid": paciente_id})]


def _aplicar(db: Session, pago: Pago, consulta_id: int, monto: Decimal) -> None:
    actual = next((a for a in pago.aplicaciones if a.consulta_id == consulta_id), None)
    if actual is not None:
        actual.monto += monto
    else:
        pago.aplicaciones.append(
            PagoAplicacion(consulta_id=consulta_id, paciente_id=pago.paciente_id, monto=monto)
        )


def sin_aplicar(pago: Pago) -> Decimal:
    if pago.anulado_en is not None:
        return CERO
    return pago.monto - sum((a.monto for a in pago.aplicaciones), CERO)


def repartir(db: Session, pago: Pago, primero: int | None = None) -> None:
    """Imputa lo que al pago le quede libre: a `primero` y luego a las más antiguas.

    Lo que sobre se queda sin aplicar: es un anticipo.
    """
    db.flush()
    libre = sin_aplicar(pago)
    saldos = _saldos(db, pago.paciente_id)
    if primero is not None:
        saldos.sort(key=lambda par: par[0] != primero)

    for consulta_id, saldo in saldos:
        if libre <= 0:
            break
        monto = min(libre, saldo)
        _aplicar(db, pago, consulta_id, monto)
        libre -= monto
    db.flush()


def aplicar_credito(db: Session, paciente_id: int) -> None:
    """Imputa los anticipos del paciente a las consultas que tengan saldo.

    Se llama cuando aparece o cambia una consulta: el paciente que pagó por
    adelantado no debe verla como pendiente.
    """
    pagos = db.scalars(
        select(Pago)
        .where(Pago.paciente_id == paciente_id, Pago.anulado_en.is_(None))
        .order_by(Pago.fecha, Pago.id)
    ).all()
    for pago in pagos:
        if sin_aplicar(pago) > 0:
            repartir(db, pago)


def registrar_pago(
    db: Session,
    paciente_id: int,
    *,
    monto: Decimal,
    metodo: str,
    fecha: date | None,
    concepto: str | None,
    referencia: str | None,
    consulta_id: int | None,
    usuario: Usuario,
) -> Pago:
    bloquear_paciente(db, paciente_id)

    if consulta_id is not None and consulta_id not in {c for c, _ in _saldos(db, paciente_id)}:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "consulta_id: esa consulta no es del paciente o no tiene saldo",
        )
    if fecha is not None and fecha > hoy():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "fecha: un pago no puede fecharse en el futuro"
        )

    pago = Pago(
        paciente_id=paciente_id,
        numero_recibo=correlativos.numero_recibo(db),
        fecha=fecha or hoy(),
        metodo=metodo,
        monto=monto,
        concepto=(concepto or "").strip() or None,
        referencia=(referencia or "").strip() or None,
        recibido_por=usuario.id,
    )
    db.add(pago)
    repartir(db, pago, primero=consulta_id)
    return pago


def anular_pago(db: Session, pago: Pago, motivo: str, usuario: Usuario) -> None:
    """Un pago no se borra: se anula. Conserva su recibo y sale de todo balance."""
    if pago.anulado_en is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "El pago ya estaba anulado")

    bloquear_paciente(db, pago.paciente_id)
    pago.aplicaciones.clear()
    pago.anulado_en = datetime.now(UTC)
    pago.anulado_por = usuario.id
    pago.motivo_anulacion = motivo.strip()
    db.flush()
    # Lo que este pago cubría vuelve a tener saldo: quizá haya otro anticipo que lo cubra.
    aplicar_credito(db, pago.paciente_id)
