"""Historial clínico del paciente: planes de tratamiento, consultas y sus líneas."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.core.deps import BD, UsuarioAuth, requiere_rol
from app.models.clinico import Cita, Consulta
from app.models.cuenta import PagoAplicacion
from app.models.enums import EstadoPlan, RolUsuario
from app.models.organizacion import Doctor, Especialidad, UnidadDental, Usuario
from app.models.paciente import Paciente
from app.models.plan import PlanItem, PlanTratamiento, Procedimiento
from app.models.servicio import Aseguradora, ListaPrecio, PrecioServicio, Servicio
from app.schemas.historial import (
    ConsultaActualizar,
    ConsultaCrear,
    ConsultaLeer,
    Historial,
    ItemActualizar,
    ItemEscribir,
    ItemLeer,
    PlanActualizar,
    PlanConConsultas,
    PlanCrear,
    PlanLeer,
)
from app.services import correlativos, cuenta, historial

router = APIRouter(tags=["historial clínico"])

# Lo clínico lo registra quien atiende. Recepción lo consulta, no lo escribe.
PuedeAtender = Annotated[Usuario, Depends(requiere_rol(RolUsuario.DOCTOR, RolUsuario.ASISTENTE))]

NO_PROCESABLE = status.HTTP_422_UNPROCESSABLE_ENTITY


def _exigir_paciente(db: Session, paciente_id: int) -> None:
    if db.get(Paciente, paciente_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El paciente no existe")


def _exigir_doctor(db: Session, doctor_id: int | None) -> None:
    if doctor_id is not None and db.get(Doctor, doctor_id) is None:
        raise HTTPException(NO_PROCESABLE, "doctor_id: el doctor no existe")


def _exigir_unidad(db: Session, unidad_id: int | None) -> None:
    if unidad_id is not None and db.get(UnidadDental, unidad_id) is None:
        raise HTTPException(NO_PROCESABLE, "unidad_id: la unidad no existe")


# --- Lectura -------------------------------------------------------------------

_SALDOS = text(
    "SELECT consulta_id, total, aplicado, saldo FROM v_saldo_consulta WHERE paciente_id = :pid"
)


def _saldos(db: Session, paciente_id: int) -> dict[int, dict[str, Decimal]]:
    """Total, cobrado y saldo de cada consulta del paciente, de `v_saldo_consulta`."""
    return {
        fila["consulta_id"]: {k: fila[k] for k in ("total", "aplicado", "saldo")}
        for fila in db.execute(_SALDOS, {"pid": paciente_id}).mappings()
    }


def _consulta_leer(consulta: Consulta, saldos: dict[int, dict[str, Decimal]]) -> ConsultaLeer:
    return ConsultaLeer.model_validate(consulta).model_copy(update=saldos.get(consulta.id, {}))


def _obtener_consulta(db: Session, consulta_id: int) -> Consulta:
    consulta = db.scalar(
        select(Consulta).where(Consulta.id == consulta_id).options(selectinload(Consulta.lineas))
    )
    if consulta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La consulta no existe")
    return consulta


def _plan_leer(db: Session, plan: PlanTratamiento) -> PlanLeer:
    """El plan con lo que el esquema no guarda: qué ítems se cumplieron y cuánto va."""
    cumplidos = set(
        db.scalars(
            select(Procedimiento.plan_item_id).where(
                Procedimiento.plan_item_id.in_([item.id for item in plan.items] or [0])
            )
        )
    )
    ejecutado = db.scalar(
        select(func.coalesce(func.sum(Procedimiento.total), 0))
        .join(Consulta, Consulta.id == Procedimiento.consulta_id)
        .where(Consulta.plan_id == plan.id)
    )
    cotizado = sum((item.total for item in plan.items), Decimal(0))
    total = (cotizado * (1 - plan.descuento_pct / 100)).quantize(Decimal("0.01"))

    lista = db.get(ListaPrecio, plan.lista_precio_id)
    aseguradora = db.get(Aseguradora, lista.aseguradora_id) if lista.aseguradora_id else None
    cobertura = Decimal(0)
    if aseguradora is not None and plan.items:
        porcentajes = dict(
            db.execute(
                select(PrecioServicio.servicio_id, PrecioServicio.cobertura_pct).where(
                    PrecioServicio.lista_precio_id == lista.id,
                    PrecioServicio.servicio_id.in_({item.servicio_id for item in plan.items}),
                )
            ).all()
        )
        factor_plan = 1 - plan.descuento_pct / 100
        cobertura = sum(
            (
                item.total * factor_plan * (porcentajes.get(item.servicio_id) or 0) / 100
                for item in plan.items
            ),
            Decimal(0),
        ).quantize(Decimal("0.01"))

    return PlanLeer.model_validate(plan).model_copy(
        update={
            "items": [
                ItemLeer.model_validate(item).model_copy(update={"ejecutado": item.id in cumplidos})
                for item in plan.items
            ],
            "cotizado": cotizado,
            "total": total,
            "ejecutado": ejecutado or Decimal(0),
            "lista_precio_nombre": lista.nombre,
            "aseguradora_nombre": aseguradora.nombre if aseguradora else None,
            "cobertura_estimada": cobertura,
        }
    )


@router.get("/pacientes/{paciente_id}/historial", response_model=Historial)
def historial_del_paciente(paciente_id: int, db: BD, _: UsuarioAuth) -> Historial:
    """Los planes con sus consultas y, aparte, las consultas sueltas. Lo más reciente primero."""
    _exigir_paciente(db, paciente_id)
    saldos = _saldos(db, paciente_id)

    consultas = db.scalars(
        select(Consulta)
        .where(Consulta.paciente_id == paciente_id)
        .options(selectinload(Consulta.lineas))
        .order_by(Consulta.fecha.desc(), Consulta.id.desc())
    ).all()
    planes = db.scalars(
        select(PlanTratamiento)
        .where(PlanTratamiento.paciente_id == paciente_id)
        .options(selectinload(PlanTratamiento.items))
        .order_by(PlanTratamiento.fecha.desc(), PlanTratamiento.id.desc())
    ).all()

    return Historial(
        planes=[
            PlanConConsultas(
                **_plan_leer(db, plan).model_dump(),
                consultas=[_consulta_leer(c, saldos) for c in consultas if c.plan_id == plan.id],
            )
            for plan in planes
        ],
        sueltas=[_consulta_leer(c, saldos) for c in consultas if c.plan_id is None],
    )


# --- Consultas -----------------------------------------------------------------


@router.post(
    "/pacientes/{paciente_id}/consultas",
    response_model=ConsultaLeer,
    status_code=status.HTTP_201_CREATED,
)
def crear_consulta(paciente_id: int, datos: ConsultaCrear, db: BD, _: PuedeAtender) -> ConsultaLeer:
    _exigir_paciente(db, paciente_id)
    _exigir_doctor(db, datos.doctor_id)
    _exigir_unidad(db, datos.unidad_id)
    plan = historial.plan_para_consulta(db, datos.plan_id, paciente_id)

    if datos.cita_id is not None:
        cita = db.get(Cita, datos.cita_id)
        if cita is None or cita.paciente_id != paciente_id:
            raise HTTPException(NO_PROCESABLE, "cita_id: la cita no es de este paciente")
    if datos.fecha is not None and datos.fecha.tzinfo is None:
        raise HTTPException(NO_PROCESABLE, "fecha: debe llevar zona horaria")

    consulta = Consulta(
        paciente_id=paciente_id,
        **datos.model_dump(exclude={"lineas", "fecha"}),
        fecha=datos.fecha or datetime.now(UTC),
    )
    db.add(consulta)
    db.flush()

    historial.guardar_lineas(db, consulta, plan, datos.lineas)
    historial.marcar_en_ejecucion(plan, consulta)
    # Quien pagó por adelantado no debe ver la consulta como pendiente.
    cuenta.aplicar_credito(db, paciente_id)
    db.commit()

    return _consulta_leer(_obtener_consulta(db, consulta.id), _saldos(db, paciente_id))


@router.get("/consultas/{consulta_id}", response_model=ConsultaLeer)
def obtener_consulta(consulta_id: int, db: BD, _: UsuarioAuth) -> ConsultaLeer:
    consulta = _obtener_consulta(db, consulta_id)
    return _consulta_leer(consulta, _saldos(db, consulta.paciente_id))


@router.patch("/consultas/{consulta_id}", response_model=ConsultaLeer)
def actualizar_consulta(
    consulta_id: int, datos: ConsultaActualizar, db: BD, _: PuedeAtender
) -> ConsultaLeer:
    consulta = _obtener_consulta(db, consulta_id)
    cambios = datos.model_dump(exclude_unset=True, exclude={"lineas"})

    if "doctor_id" in cambios:
        if cambios["doctor_id"] is None:
            raise HTTPException(NO_PROCESABLE, "doctor_id: no puede quedar vacío")
        _exigir_doctor(db, cambios["doctor_id"])
    if "unidad_id" in cambios:
        _exigir_unidad(db, cambios["unidad_id"])
    if "fecha" in cambios and (cambios["fecha"] is None or cambios["fecha"].tzinfo is None):
        raise HTTPException(NO_PROCESABLE, "fecha: debe llevar zona horaria")

    plan_id = cambios.get("plan_id", consulta.plan_id)
    plan = (
        historial.plan_para_consulta(db, plan_id, consulta.paciente_id)
        if "plan_id" in cambios or datos.lineas is not None
        else None
    )

    for campo, valor in cambios.items():
        setattr(consulta, campo, valor)
    db.flush()

    if datos.lineas is not None:
        historial.guardar_lineas(db, consulta, plan, datos.lineas)
        historial.marcar_en_ejecucion(plan, consulta)

        # Si la consulta quedó por debajo de lo ya cobrado, el exceso no se
        # pierde: sale de la aplicación y vuelve a ser crédito del paciente.
        total = sum((linea.total for linea in consulta.lineas), Decimal(0))
        aplicaciones = db.scalars(
            select(PagoAplicacion)
            .where(PagoAplicacion.consulta_id == consulta.id)
            .order_by(PagoAplicacion.id.desc())
        ).all()
        exceso = sum((a.monto for a in aplicaciones), Decimal(0)) - total
        for aplicacion in aplicaciones:
            if exceso <= 0:
                break
            quita = min(aplicacion.monto, exceso)
            exceso -= quita
            if quita == aplicacion.monto:
                db.delete(aplicacion)
            else:
                aplicacion.monto -= quita
        db.flush()
        cuenta.aplicar_credito(db, consulta.paciente_id)

    db.commit()
    return _consulta_leer(_obtener_consulta(db, consulta_id), _saldos(db, consulta.paciente_id))


@router.delete("/consultas/{consulta_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_consulta(consulta_id: int, db: BD, _: PuedeAtender) -> None:
    """Sólo una consulta sin cobros: lo cobrado es historia contable."""
    consulta = _obtener_consulta(db, consulta_id)

    if db.scalar(
        select(PagoAplicacion.id).where(PagoAplicacion.consulta_id == consulta_id).limit(1)
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La consulta tiene pagos aplicados: no se puede eliminar",
        )
    db.execute(
        text("UPDATE odontograma SET consulta_id = NULL WHERE consulta_id = :id"),
        {"id": consulta_id},
    )
    historial.guardar_lineas(db, consulta, None, [])
    db.delete(consulta)
    db.commit()


# --- Planes de tratamiento -----------------------------------------------------


def _obtener_plan(db: Session, plan_id: int) -> PlanTratamiento:
    plan = db.scalar(
        select(PlanTratamiento)
        .where(PlanTratamiento.id == plan_id)
        .options(selectinload(PlanTratamiento.items))
    )
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El plan de tratamiento no existe")
    return plan


def _exigir_especialidad(db: Session, especialidad_id: int | None) -> None:
    if especialidad_id is not None and db.get(Especialidad, especialidad_id) is None:
        raise HTTPException(NO_PROCESABLE, "especialidad_id: la especialidad no existe")


def _exigir_abierto(plan: PlanTratamiento) -> None:
    if not plan.estado.abierto:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"El plan {plan.codigo} está {plan.estado.value}: reábrelo para modificarlo",
        )


@router.post(
    "/pacientes/{paciente_id}/planes", response_model=PlanLeer, status_code=status.HTTP_201_CREATED
)
def crear_plan(paciente_id: int, datos: PlanCrear, db: BD, _: PuedeAtender) -> PlanLeer:
    _exigir_paciente(db, paciente_id)
    _exigir_doctor(db, datos.doctor_id)
    _exigir_especialidad(db, datos.especialidad_id)

    plan = PlanTratamiento(
        paciente_id=paciente_id,
        codigo=correlativos.codigo_plan(db),
        **datos.model_dump(exclude={"lista_precio_id"}),
        lista_precio_id=historial.lista_del_plan(db, datos.lista_precio_id),
    )
    db.add(plan)
    db.commit()
    return _plan_leer(db, _obtener_plan(db, plan.id))


@router.get("/planes/{plan_id}", response_model=PlanLeer)
def obtener_plan(plan_id: int, db: BD, _: UsuarioAuth) -> PlanLeer:
    return _plan_leer(db, _obtener_plan(db, plan_id))


@router.patch("/planes/{plan_id}", response_model=PlanLeer)
def actualizar_plan(plan_id: int, datos: PlanActualizar, db: BD, _: PuedeAtender) -> PlanLeer:
    plan = _obtener_plan(db, plan_id)
    cambios = datos.model_dump(exclude_unset=True)

    if cambios.get("estado") is not None:
        era_rechazado = plan.estado == EstadoPlan.RECHAZADO
        historial.cambiar_estado_plan(plan, cambios.pop("estado"))
        if era_rechazado != (plan.estado == EstadoPlan.RECHAZADO):
            historial.repintar_plan(db, plan)
    cambios.pop("estado", None)

    if cambios:
        _exigir_abierto(plan)
    if "doctor_id" in cambios:
        if cambios["doctor_id"] is None:
            raise HTTPException(NO_PROCESABLE, "doctor_id: no puede quedar vacío")
        _exigir_doctor(db, cambios["doctor_id"])
    if "especialidad_id" in cambios:
        _exigir_especialidad(db, cambios["especialidad_id"])
    if "descuento_pct" in cambios and cambios["descuento_pct"] is None:
        cambios["descuento_pct"] = Decimal(0)

    for campo, valor in cambios.items():
        setattr(plan, campo, valor)

    db.commit()
    return _plan_leer(db, _obtener_plan(db, plan_id))


@router.delete("/planes/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_plan(plan_id: int, db: BD, _: PuedeAtender) -> None:
    """Sólo un plan sin consultas: con ellas es historia clínica."""
    plan = _obtener_plan(db, plan_id)
    if db.scalar(select(Consulta.id).where(Consulta.plan_id == plan_id).limit(1)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"El plan {plan.codigo} tiene consultas: finalízalo en lugar de eliminarlo",
        )
    for item in plan.items:
        historial.despintar_item(db, plan, item)
    db.delete(plan)
    db.commit()


# --- Ítems del plan ------------------------------------------------------------


def _item(plan: PlanTratamiento, item_id: int) -> PlanItem:
    item = next((i for i in plan.items if i.id == item_id), None)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El ítem no pertenece a este plan")
    return item


def _item_ejecutado(db: Session, item_id: int) -> bool:
    return (
        db.scalar(select(Procedimiento.id).where(Procedimiento.plan_item_id == item_id).limit(1))
        is not None
    )


@router.post(
    "/planes/{plan_id}/items", response_model=PlanLeer, status_code=status.HTTP_201_CREATED
)
def crear_item(plan_id: int, datos: ItemEscribir, db: BD, _: PuedeAtender) -> PlanLeer:
    plan = _obtener_plan(db, plan_id)
    _exigir_abierto(plan)

    servicio = db.get(Servicio, datos.servicio_id)
    if servicio is None:
        raise HTTPException(NO_PROCESABLE, "servicio_id: el servicio no existe")
    historial.validar_pieza_y_caras(db, servicio, datos.codigo_fdi, datos.superficies, "ítem")

    valores = datos.model_dump()
    if valores["precio_unit"] is None:
        valores["precio_unit"] = historial.precio_de(db, servicio, plan.lista_precio_id)
    item = PlanItem(**valores)
    plan.items.append(item)
    db.flush()
    db.refresh(item)
    historial.pintar_item(db, plan, item)

    db.commit()
    return _plan_leer(db, _obtener_plan(db, plan_id))


@router.patch("/planes/{plan_id}/items/{item_id}", response_model=PlanLeer)
def actualizar_item(
    plan_id: int, item_id: int, datos: ItemActualizar, db: BD, _: PuedeAtender
) -> PlanLeer:
    plan = _obtener_plan(db, plan_id)
    _exigir_abierto(plan)
    item = _item(plan, item_id)
    cambios = datos.model_dump(exclude_unset=True)

    ejecutado = _item_ejecutado(db, item_id)
    anulables = {"codigo_fdi", "superficies"}
    # Lo ya ejecutado está cobrado con esa pieza y ese precio: sólo admite reordenarse.
    if ejecutado and set(cambios) - {"fase", "prioridad", "aprobado"}:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"«{item.servicio.nombre}» ya se ejecutó: sólo se puede cambiar su fase o prioridad",
        )
    for campo, valor in cambios.items():
        if valor is None and campo not in anulables:
            raise HTTPException(NO_PROCESABLE, f"{campo}: no puede quedar vacío")
        setattr(item, campo, valor)

    historial.validar_pieza_y_caras(db, item.servicio, item.codigo_fdi, item.superficies, "ítem")
    if not ejecutado and {"codigo_fdi", "superficies"} & set(cambios):
        db.flush()
        historial.despintar_item(db, plan, item)
        historial.pintar_item(db, plan, item)
    db.commit()
    return _plan_leer(db, _obtener_plan(db, plan_id))


@router.delete("/planes/{plan_id}/items/{item_id}", response_model=PlanLeer)
def borrar_item(plan_id: int, item_id: int, db: BD, _: PuedeAtender) -> PlanLeer:
    plan = _obtener_plan(db, plan_id)
    _exigir_abierto(plan)
    item = _item(plan, item_id)

    if _item_ejecutado(db, item_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"«{item.servicio.nombre}» ya se ejecutó en una consulta: no se puede quitar del plan",
        )
    historial.despintar_item(db, plan, item)
    plan.items.remove(item)
    db.commit()
    return _plan_leer(db, _obtener_plan(db, plan_id))
