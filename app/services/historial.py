"""Consultas, líneas ejecutadas y planes: lo que el esquema no puede garantizar.

Aquí vive la idea de que **se pinta una vez**: una línea ejecutada sobre una
pieza deja en el odontograma la condición que su servicio declara
(`servicio.condicion_resultante_id`), de modo que lo hecho, lo dibujado y lo
cobrado no puedan discrepar.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.tiempo import hoy, local
from app.models.catalogo import Diente
from app.models.clinico import Consulta
from app.models.enums import AmbitoCondicion, Denticion, EstadoHallazgo, EstadoPlan
from app.models.odontograma import OdontogramaHallazgo
from app.models.plan import PlanItem, PlanTratamiento, Procedimiento
from app.models.servicio import ListaPrecio, PrecioServicio, Servicio
from app.schemas.historial import LineaEscribir
from app.services import inventario as servicio_inventario
from app.services import odontograma as servicio_odontograma
from app.services.catalogo import lista_particular

NO_PROCESABLE = status.HTTP_422_UNPROCESSABLE_ENTITY


# --- Precios -------------------------------------------------------------------


def precio_de(db: Session, servicio: Servicio, lista_precio_id: int | None) -> Decimal:
    """Precio del servicio en la tarifa pedida; si no lo tiene ahí, en la particular."""
    particular = lista_particular(db).id
    for lista_id in dict.fromkeys([lista_precio_id or particular, particular]):
        precio = db.scalar(
            select(PrecioServicio.precio).where(
                PrecioServicio.servicio_id == servicio.id,
                PrecioServicio.lista_precio_id == lista_id,
            )
        )
        if precio is not None:
            return precio
    raise HTTPException(NO_PROCESABLE, f"«{servicio.nombre}» no tiene precio en ninguna tarifa")


# --- Piezas y caras ------------------------------------------------------------


def validar_pieza_y_caras(
    db: Session, servicio: Servicio, codigo_fdi: int | None, superficies: str | None, donde: str
) -> None:
    """Lo que el servicio exige sobre la pieza, antes de guardar nada."""
    if servicio.requiere_diente and codigo_fdi is None:
        raise HTTPException(NO_PROCESABLE, f"{donde}: «{servicio.nombre}» se hace sobre una pieza")
    if superficies and codigo_fdi is None:
        raise HTTPException(NO_PROCESABLE, f"{donde}: hay caras pero no pieza")
    if codigo_fdi is None:
        return

    diente = db.get(Diente, codigo_fdi)
    if diente is None:
        raise HTTPException(NO_PROCESABLE, f"{donde}: la pieza {codigo_fdi} no existe")

    if servicio.requiere_superficie and not superficies:
        raise HTTPException(NO_PROCESABLE, f"{donde}: «{servicio.nombre}» pide al menos una cara")
    for cara in superficies or "":
        # Oclusal sólo en posteriores, incisal sólo en anteriores.
        if (cara == "O" and diente.grupo.es_anterior) or (
            cara == "I" and not diente.grupo.es_anterior
        ):
            raise HTTPException(
                NO_PROCESABLE,
                f"{donde}: la pieza {codigo_fdi} es un {diente.grupo.value} y no tiene cara {cara}",
            )


# --- Odontograma ---------------------------------------------------------------


def pintar_linea(db: Session, linea: Procedimiento) -> None:
    """Deja en el odontograma vigente lo que la línea ejecutada hizo.

    Se escribe sobre la versión vigente —no se abre una nueva por consulta— para
    no perder lo planificado, que no se hereda entre versiones. Si en esa cara
    había una propuesta del mismo tratamiento, pasa a completada en lugar de
    duplicarse.

    Nunca bloquea el registro clínico: si la pieza no cabe en el odontograma
    (una temporal en uno de dentición permanente) la línea se guarda igual y el
    dibujo no se toca.
    """
    condicion = linea.servicio.condicion_resultante
    if condicion is None or linea.codigo_fdi is None:
        return

    diente = db.get(Diente, linea.codigo_fdi)
    vigente = servicio_odontograma.obtener_vigente(db, linea.paciente_id)
    if vigente is None:
        vigente = servicio_odontograma.crear_version(
            db, linea.paciente_id, denticion=diente.denticion, doctor_id=linea.doctor_id
        )
    if diente.denticion != vigente.denticion:
        return

    # Un tratamiento de pieza completa (corona, implante) no lleva cara.
    caras: list[str | None] = (
        list(linea.superficies)
        if linea.superficies and condicion.ambito == AmbitoCondicion.SUPERFICIE
        else [None]
    )

    for cara in caras:
        existentes = db.scalars(
            select(OdontogramaHallazgo).where(
                OdontogramaHallazgo.odontograma_id == vigente.id,
                OdontogramaHallazgo.codigo_fdi == linea.codigo_fdi,
                OdontogramaHallazgo.superficie.is_(cara)
                if cara is None
                else OdontogramaHallazgo.superficie == cara,
                OdontogramaHallazgo.condicion_dental_id == condicion.id,
            )
        ).all()

        hecho = next((h for h in existentes if h.estado == EstadoHallazgo.COMPLETADO), None)
        propuesto = next(
            (
                h
                for h in existentes
                if h.estado in (EstadoHallazgo.PLANIFICADO, EstadoHallazgo.EN_PROCESO)
            ),
            None,
        )
        if hecho is not None:
            continue
        if propuesto is not None:
            propuesto.estado = EstadoHallazgo.COMPLETADO
            propuesto.procedimiento_id = linea.id
            propuesto.fecha = linea.fecha
            propuesto.doctor_id = linea.doctor_id
            continue
        db.add(
            OdontogramaHallazgo(
                odontograma_id=vigente.id,
                codigo_fdi=linea.codigo_fdi,
                superficie=cara,
                condicion_dental_id=condicion.id,
                estado=EstadoHallazgo.COMPLETADO,
                doctor_id=linea.doctor_id,
                fecha=linea.fecha,
                procedimiento_id=linea.id,
            )
        )
    db.flush()


def despintar_linea(db: Session, linea: Procedimiento) -> None:
    """Quita del odontograma vigente lo que pintó una línea que se elimina.

    Sólo lo que esa línea creó: un hallazgo marcado a mano no se toca. Lo que
    venía de un ítem del plan no desaparece: vuelve a quedar como propuesto.
    """
    vigente = servicio_odontograma.obtener_vigente(db, linea.paciente_id)
    if vigente is None:
        return
    for hallazgo in db.scalars(
        select(OdontogramaHallazgo).where(
            OdontogramaHallazgo.odontograma_id == vigente.id,
            OdontogramaHallazgo.procedimiento_id == linea.id,
        )
    ):
        if hallazgo.plan_item_id is not None:
            hallazgo.estado = EstadoHallazgo.PLANIFICADO
            hallazgo.procedimiento_id = None
        else:
            db.delete(hallazgo)
    db.flush()


# --- Lo planificado: los ítems del plan en el odontograma ------------------------


def pintar_item(db: Session, plan: PlanTratamiento, item: PlanItem) -> None:
    """Deja en el odontograma vigente, como «planificado», lo que el ítem propone.

    Es la otra mitad de «se pinta una vez»: el plan visual sale del presupuesto,
    sin dibujarlo aparte. Si esa cara ya tiene la misma condición —hecha, en
    proceso o propuesta a mano— no se duplica.
    """
    condicion = item.servicio.condicion_resultante
    if condicion is None or item.codigo_fdi is None:
        return

    diente = db.get(Diente, item.codigo_fdi)
    vigente = servicio_odontograma.obtener_vigente(db, plan.paciente_id)
    if vigente is None:
        vigente = servicio_odontograma.crear_version(
            db, plan.paciente_id, denticion=diente.denticion, doctor_id=plan.doctor_id
        )
    if diente.denticion != vigente.denticion:
        return

    caras: list[str | None] = (
        list(item.superficies)
        if item.superficies and condicion.ambito == AmbitoCondicion.SUPERFICIE
        else [None]
    )
    for cara in caras:
        ya_esta = db.scalar(
            select(OdontogramaHallazgo.id)
            .where(
                OdontogramaHallazgo.odontograma_id == vigente.id,
                OdontogramaHallazgo.codigo_fdi == item.codigo_fdi,
                OdontogramaHallazgo.superficie.is_(cara)
                if cara is None
                else OdontogramaHallazgo.superficie == cara,
                OdontogramaHallazgo.condicion_dental_id == condicion.id,
                OdontogramaHallazgo.estado != EstadoHallazgo.ANULADO,
            )
            .limit(1)
        )
        if ya_esta:
            continue
        db.add(
            OdontogramaHallazgo(
                odontograma_id=vigente.id,
                codigo_fdi=item.codigo_fdi,
                superficie=cara,
                condicion_dental_id=condicion.id,
                estado=EstadoHallazgo.PLANIFICADO,
                doctor_id=plan.doctor_id,
                fecha=hoy(),
                plan_item_id=item.id,
            )
        )
    db.flush()


def despintar_item(db: Session, plan: PlanTratamiento, item: PlanItem) -> None:
    """Quita la propuesta que pintó el ítem. Lo ya ejecutado se queda."""
    vigente = servicio_odontograma.obtener_vigente(db, plan.paciente_id)
    if vigente is None or item.id is None:
        return
    for hallazgo in db.scalars(
        select(OdontogramaHallazgo).where(
            OdontogramaHallazgo.odontograma_id == vigente.id,
            OdontogramaHallazgo.plan_item_id == item.id,
            OdontogramaHallazgo.estado == EstadoHallazgo.PLANIFICADO,
        )
    ):
        db.delete(hallazgo)
    db.flush()


def repintar_plan(db: Session, plan: PlanTratamiento) -> None:
    """Un plan rechazado deja de proponer; uno que se reabre vuelve a hacerlo."""
    ejecutados = set(
        db.scalars(
            select(Procedimiento.plan_item_id).where(
                Procedimiento.plan_item_id.in_([i.id for i in plan.items])
            )
        )
    )
    for item in plan.items:
        despintar_item(db, plan, item)
        if plan.estado != EstadoPlan.RECHAZADO and item.id not in ejecutados:
            pintar_item(db, plan, item)


# --- Líneas de una consulta ----------------------------------------------------

_BLOQUEAN_BORRADO = text(
    "SELECT EXISTS (SELECT 1 FROM factura_item fi JOIN factura f ON f.id = fi.factura_id "
    "               WHERE fi.procedimiento_id = :id AND f.estado <> 'anulada') "
    "    OR EXISTS (SELECT 1 FROM implante WHERE procedimiento_id = :id)"
)


def _descuento_del_plan(item: PlanItem, plan: PlanTratamiento) -> Decimal:
    """El descuento del plan se copia a la línea al ejecutarla, combinado con el
    del ítem: así el cargo no depende de un join al plan."""
    factor = (1 - item.descuento_pct / 100) * (1 - plan.descuento_pct / 100)
    return ((1 - factor) * 100).quantize(Decimal("0.01"))


def guardar_lineas(
    db: Session, consulta: Consulta, plan: PlanTratamiento | None, datos: list[LineaEscribir]
) -> None:
    """Deja en la consulta exactamente las líneas de `datos`.

    Las que traen `id` se actualizan, las nuevas se crean y las que faltan se
    eliminan; cada cambio se refleja en el odontograma.
    """
    actuales = {linea.id: linea for linea in consulta.lineas}
    conservadas: set[int] = set()
    fecha_consulta: date = local(consulta.fecha).date() if consulta.fecha else hoy()

    for posicion, dato in enumerate(datos, start=1):
        donde = f"línea {posicion}"
        servicio = db.get(Servicio, dato.servicio_id)
        if servicio is None:
            raise HTTPException(NO_PROCESABLE, f"{donde}: el servicio no existe")
        validar_pieza_y_caras(db, servicio, dato.codigo_fdi, dato.superficies, donde)

        item: PlanItem | None = None
        if dato.plan_item_id is not None:
            item = db.get(PlanItem, dato.plan_item_id)
            if item is None or plan is None or item.plan_id != plan.id:
                raise HTTPException(
                    NO_PROCESABLE, f"{donde}: el ítem no pertenece al plan de esta consulta"
                )

        precio = dato.precio
        if precio is None:
            precio = (
                item.precio_unit
                if item is not None
                else precio_de(db, servicio, plan.lista_precio_id if plan else None)
            )
        descuento = dato.descuento_pct
        if item is not None and plan is not None and "descuento_pct" not in dato.model_fields_set:
            descuento = _descuento_del_plan(item, plan)

        valores = {
            "servicio_id": servicio.id,
            "codigo_fdi": dato.codigo_fdi,
            "superficies": dato.superficies,
            "cantidad": dato.cantidad,
            "precio": precio,
            "descuento_pct": descuento,
            "plan_item_id": dato.plan_item_id,
            "notas": (dato.notas or "").strip() or None,
            "doctor_id": consulta.doctor_id,
            "fecha": fecha_consulta,
        }

        if dato.id is not None:
            linea = actuales.get(dato.id)
            if linea is None:
                raise HTTPException(NO_PROCESABLE, f"{donde}: no pertenece a esta consulta")
            # Si cambió lo que se dibuja, se borra lo viejo y se pinta lo nuevo.
            redibujar = (linea.servicio_id, linea.codigo_fdi, linea.superficies) != (
                servicio.id,
                dato.codigo_fdi,
                dato.superficies,
            )
            # Otro servicio u otra cantidad gastan otros insumos.
            reconsumir = (linea.servicio_id, linea.cantidad) != (servicio.id, dato.cantidad)
            if redibujar:
                despintar_linea(db, linea)
            if reconsumir:
                servicio_inventario.devolver_linea(db, linea)
            for campo, valor in valores.items():
                setattr(linea, campo, valor)
            conservadas.add(linea.id)
            db.flush()
            db.refresh(linea)
            if redibujar:
                pintar_linea(db, linea)
            if reconsumir:
                servicio_inventario.consumir_linea(db, linea)
        else:
            linea = Procedimiento(paciente_id=consulta.paciente_id, **valores)
            consulta.lineas.append(linea)
            db.flush()
            db.refresh(linea)
            pintar_linea(db, linea)
            servicio_inventario.consumir_linea(db, linea)

    for linea_id, linea in actuales.items():
        if linea_id in conservadas:
            continue
        if db.execute(_BLOQUEAN_BORRADO, {"id": linea_id}).scalar():
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"«{linea.servicio.nombre}» ya está en una factura o tiene un implante "
                "registrado: no se puede quitar de la consulta",
            )
        despintar_linea(db, linea)
        servicio_inventario.devolver_linea(db, linea)
        consulta.lineas.remove(linea)
    db.flush()


# --- Planes --------------------------------------------------------------------


def obtener_plan(db: Session, plan_id: int) -> PlanTratamiento:
    plan = db.get(PlanTratamiento, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El plan de tratamiento no existe")
    return plan


def plan_para_consulta(
    db: Session, plan_id: int | None, paciente_id: int
) -> PlanTratamiento | None:
    """El plan del que colgará la consulta, si es de ese paciente y sigue abierto."""
    if plan_id is None:
        return None
    plan = db.get(PlanTratamiento, plan_id)
    if plan is None or plan.paciente_id != paciente_id:
        raise HTTPException(NO_PROCESABLE, "plan_id: el plan no es de este paciente")
    if not plan.estado.abierto:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"El plan {plan.codigo} está {plan.estado.value}: reábrelo para añadirle consultas",
        )
    return plan


def marcar_en_ejecucion(plan: PlanTratamiento | None, consulta: Consulta) -> None:
    """Con la primera línea ejecutada el plan pasa solo a «en ejecución»."""
    if plan is None or not consulta.lineas:
        return
    if plan.estado in (EstadoPlan.BORRADOR, EstadoPlan.PRESENTADO, EstadoPlan.ACEPTADO):
        plan.estado = EstadoPlan.EN_EJECUCION


def cambiar_estado_plan(plan: PlanTratamiento, nuevo: EstadoPlan) -> None:
    if nuevo == plan.estado:
        return
    if nuevo not in plan.estado.siguientes:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Un plan «{plan.estado.value}» no puede pasar a «{nuevo.value}»",
        )
    plan.estado = nuevo
    plan.cerrado_en = datetime.now(UTC) if nuevo == EstadoPlan.FINALIZADO else None


def lista_del_plan(db: Session, lista_precio_id: int | None) -> int:
    if lista_precio_id is None:
        return lista_particular(db).id
    if db.get(ListaPrecio, lista_precio_id) is None:
        raise HTTPException(NO_PROCESABLE, "lista_precio_id: la tarifa no existe")
    return lista_precio_id


def denticion_de(db: Session, codigo_fdi: int) -> Denticion:
    return db.get(Diente, codigo_fdi).denticion
