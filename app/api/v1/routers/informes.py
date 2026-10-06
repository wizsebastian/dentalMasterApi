"""Reporte de un doctor: producción, cobros, comisión y lo que se le ha pagado."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import text

from app.core.config import settings
from app.core.deps import BD, UsuarioAuth
from app.core.tiempo import hoy
from app.models.enums import RolUsuario
from app.models.organizacion import Doctor
from app.schemas.informes import (
    CitasDelDoctor,
    CobroDelDoctor,
    LineaRealizada,
    PagoAlDoctor,
    ReporteDoctor,
    ServicioRealizado,
)

router = APIRouter(tags=["informes"])

CERO = Decimal(0)

# Las mismas definiciones que la fila del doctor en `/informes/resumen`:
# producción por la fecha de la línea, cobrado por la fecha del pago.
_LINEAS = text(
    "SELECT pr.id AS procedimiento_id, pr.fecha, pr.paciente_id, "
    "       p.nombres || ' ' || p.apellidos AS paciente_nombre, "
    "       s.codigo AS servicio_codigo, s.nombre AS servicio_nombre, "
    "       pr.codigo_fdi, pr.superficies, pr.cantidad, pr.total "
    "FROM procedimiento pr "
    "JOIN paciente p ON p.id = pr.paciente_id "
    "JOIN servicio s ON s.id = pr.servicio_id "
    "WHERE pr.doctor_id = :doctor AND pr.estado IN ('en_proceso','completado') "
    "  AND pr.fecha BETWEEN :desde AND :hasta "
    "ORDER BY pr.fecha, pr.id"
)

_COBROS = text(
    "SELECT pg.fecha, pg.numero_recibo, pg.id AS pago_id, c.paciente_id, "
    "       p.nombres || ' ' || p.apellidos AS paciente_nombre, "
    "       (c.fecha AT TIME ZONE :zona)::date AS consulta_fecha, a.monto "
    "FROM pago_aplicacion a "
    "JOIN pago pg ON pg.id = a.pago_id AND pg.anulado_en IS NULL "
    "JOIN consulta c ON c.id = a.consulta_id "
    "JOIN paciente p ON p.id = c.paciente_id "
    "WHERE c.doctor_id = :doctor AND pg.fecha BETWEEN :desde AND :hasta "
    "ORDER BY pg.fecha, pg.numero_recibo"
)

_PAGOS = text(
    "SELECT g.id AS gasto_id, g.fecha, g.descripcion, g.metodo, g.monto "
    "FROM gasto g "
    "WHERE g.doctor_id = :doctor AND g.anulado_en IS NULL "
    "  AND g.fecha BETWEEN :desde AND :hasta "
    "ORDER BY g.fecha, g.id"
)

_CONSULTAS = text(
    "SELECT count(*) AS consultas, count(DISTINCT paciente_id) AS pacientes "
    "FROM consulta "
    "WHERE doctor_id = :doctor AND (fecha AT TIME ZONE :zona)::date BETWEEN :desde AND :hasta"
)

_CITAS = text(
    "SELECT estado::text, count(*) FROM cita "
    "WHERE doctor_id = :doctor AND (inicio AT TIME ZONE :zona)::date BETWEEN :desde AND :hasta "
    "GROUP BY estado"
)

_POR_COBRAR = text(
    "SELECT COALESCE(SUM(saldo), 0) FROM v_saldo_consulta WHERE doctor_id = :doctor AND saldo > 0"
)


@router.get("/informes/doctores/{doctor_id}", response_model=ReporteDoctor)
def reporte_del_doctor(
    doctor_id: int,
    db: BD,
    usuario: UsuarioAuth,
    desde: Annotated[date | None, Query(description="Por defecto, el día 1 del mes")] = None,
    hasta: Annotated[date | None, Query(description="Incluido. Por defecto, hoy")] = None,
) -> ReporteDoctor:
    """El reporte de un doctor en un tramo de fechas.

    Lo ve quien lleva las cuentas, y cada doctor el suyo: nunca el de un colega.
    """
    lleva_cuentas = usuario.rol in (RolUsuario.ADMIN, RolUsuario.FACTURACION)
    es_el_suyo = usuario.rol == RolUsuario.DOCTOR and usuario.doctor_id == doctor_id
    if not (lleva_cuentas or es_el_suyo):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Sólo puedes ver tu propio reporte de producción"
        )

    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El doctor no existe")

    hasta = hasta or hoy()
    desde = desde or hasta.replace(day=1)
    if hasta < desde:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "hasta: anterior a desde")

    tramo = {"doctor": doctor_id, "desde": desde, "hasta": hasta}
    con_zona = {**tramo, "zona": settings.zona_horaria}

    filas = db.execute(_LINEAS, tramo).mappings().all()
    cobros = [CobroDelDoctor(**f) for f in db.execute(_COBROS, con_zona).mappings()]
    pagos = [PagoAlDoctor(**f) for f in db.execute(_PAGOS, tramo).mappings()]

    # Qué hizo, agrupado: de lo que más produjo a lo que menos.
    por_servicio: dict[str, ServicioRealizado] = {}
    for fila in filas:
        servicio = por_servicio.setdefault(
            fila["servicio_codigo"],
            ServicioRealizado(
                servicio_codigo=fila["servicio_codigo"],
                servicio_nombre=fila["servicio_nombre"],
                cantidad=0,
                produccion=CERO,
            ),
        )
        servicio.cantidad += fila["cantidad"]
        servicio.produccion += fila["total"]

    produccion = sum((f["total"] for f in filas), CERO)
    cobrado = sum((c.monto for c in cobros), CERO)
    pagado = sum((p.monto for p in pagos), CERO)
    comision_pct = doctor.porcentaje_comision or CERO
    comision = (cobrado * comision_pct / 100).quantize(Decimal("0.01"))

    conteo = db.execute(_CONSULTAS, con_zona).one()
    citas = dict(db.execute(_CITAS, con_zona).all())

    return ReporteDoctor(
        doctor_id=doctor.id,
        doctor_nombre=doctor.nombre_completo,
        especialidades=[
            e.nombre
            for e in db.execute(
                text(
                    "SELECT e.nombre FROM doctor_especialidad de "
                    "JOIN especialidad e ON e.id = de.especialidad_id "
                    "WHERE de.doctor_id = :doctor ORDER BY de.principal DESC, e.nombre"
                ),
                {"doctor": doctor_id},
            )
        ],
        desde=desde,
        hasta=hasta,
        produccion=produccion,
        cobrado=cobrado,
        comision_pct=comision_pct,
        comision=comision,
        pagado=pagado,
        por_liquidar=comision - pagado,
        por_cobrar=db.execute(_POR_COBRAR, {"doctor": doctor_id}).scalar_one(),
        consultas=conteo.consultas,
        pacientes=conteo.pacientes,
        citas=CitasDelDoctor(
            total=sum(citas.values()),
            atendidas=citas.get("atendida", 0),
            no_asistio=citas.get("no_asistio", 0),
            canceladas=citas.get("cancelada", 0),
        ),
        servicios=sorted(por_servicio.values(), key=lambda s: s.produccion, reverse=True),
        lineas=[
            LineaRealizada(**{k: v for k, v in f.items() if k != "servicio_codigo"}) for f in filas
        ],
        cobros=cobros,
        pagos=pagos,
    )
