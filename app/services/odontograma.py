"""Reglas de negocio del odontograma.

El esquema garantiza que sólo haya un odontograma vigente por paciente (índice
parcial `uq_odontograma_actual`), pero no puede garantizar lo demás: que las
versiones pasadas sean de solo lectura, ni que una cara exista en la pieza donde
se registra. Eso vive aquí.
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tiempo import hoy
from app.models.catalogo import CondicionDental, Diente
from app.models.enums import AmbitoCondicion, Denticion, EstadoHallazgo
from app.models.odontograma import Odontograma, OdontogramaDiente, OdontogramaHallazgo

# Estados que se arrastran al crear una versión nueva. Lo planificado a mano no
# se copia: arrastrarlo duplicaría propuestas que quizá ya se descartaron. Lo
# que propuso un ítem de un plan sí viaja (`plan_item_id`), porque el plan es
# quien lo mantiene: se quita solo cuando el ítem se quita o se ejecuta.
ESTADOS_HEREDABLES = (EstadoHallazgo.EXISTENTE, EstadoHallazgo.COMPLETADO)


def se_hereda(hallazgo: OdontogramaHallazgo) -> bool:
    if hallazgo.estado in ESTADOS_HEREDABLES:
        return True
    return hallazgo.estado == EstadoHallazgo.PLANIFICADO and hallazgo.plan_item_id is not None


def obtener_vigente(db: Session, paciente_id: int) -> Odontograma | None:
    return db.scalar(
        select(Odontograma).where(Odontograma.paciente_id == paciente_id, Odontograma.es_actual)
    )


def exigir_vigente(db: Session, odontograma_id: int) -> Odontograma:
    """Devuelve el odontograma sólo si admite escritura.

    Un odontograma histórico es un documento clínico cerrado: se consulta, no se
    corrige. Para registrar algo nuevo hay que abrir la versión N+1.
    """
    odontograma = db.get(Odontograma, odontograma_id)
    if odontograma is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El odontograma no existe")

    if not odontograma.es_actual:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"El odontograma v{odontograma.version} es histórico y no admite cambios. "
            "Crea una versión nueva para registrar hallazgos.",
        )
    return odontograma


def crear_version(
    db: Session,
    paciente_id: int,
    *,
    denticion: Denticion = Denticion.PERMANENTE,
    doctor_id: int | None = None,
    observaciones: str | None = None,
    copiar_hallazgos: bool = True,
) -> Odontograma:
    """Cierra la versión vigente y abre la siguiente, en una sola transacción.

    El orden importa: hay que quitar `es_actual` de la anterior y descargar ese
    UPDATE antes de insertar la nueva, o el índice parcial rechaza el INSERT por
    tener dos filas vigentes a la vez.
    """
    anterior = obtener_vigente(db, paciente_id)

    if anterior is not None:
        anterior.es_actual = False
        db.flush()

    nueva = Odontograma(
        paciente_id=paciente_id,
        doctor_id=doctor_id,
        version=(anterior.version + 1) if anterior else 1,
        denticion=denticion,
        fecha=hoy(),
        es_actual=True,
        observaciones=observaciones,
    )
    db.add(nueva)
    db.flush()

    # Al cambiar de dentición no hay nada que arrastrar: son otras piezas.
    if anterior is not None and copiar_hallazgos and anterior.denticion == denticion:
        for previo in anterior.hallazgos:
            if not se_hereda(previo):
                continue
            db.add(
                OdontogramaHallazgo(
                    odontograma_id=nueva.id,
                    codigo_fdi=previo.codigo_fdi,
                    superficie=previo.superficie,
                    condicion_dental_id=previo.condicion_dental_id,
                    estado=previo.estado,
                    doctor_id=previo.doctor_id,
                    fecha=previo.fecha,
                    notas=previo.notas,
                    procedimiento_id=previo.procedimiento_id,
                    plan_item_id=previo.plan_item_id,
                )
            )
        for previo_diente in anterior.dientes:
            db.add(
                OdontogramaDiente(
                    odontograma_id=nueva.id,
                    codigo_fdi=previo_diente.codigo_fdi,
                    presente=previo_diente.presente,
                    movilidad=previo_diente.movilidad,
                    recesion_mm=previo_diente.recesion_mm,
                    sondaje_mm=previo_diente.sondaje_mm,
                    sangrado=previo_diente.sangrado,
                    notas=previo_diente.notas,
                )
            )
        db.flush()

    return nueva


def validar_pieza(db: Session, odontograma: Odontograma, codigo_fdi: int) -> Diente:
    """Comprueba que la pieza exista y pertenezca a la dentición del odontograma.

    La clave foránea ya rechaza un código FDI inexistente; lo que no ve es que
    un odontograma de dentición permanente no puede registrar piezas temporales.
    """
    diente = db.get(Diente, codigo_fdi)
    if diente is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"La pieza {codigo_fdi} no existe"
        )

    if diente.denticion != odontograma.denticion:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"La pieza {codigo_fdi} es de dentición {diente.denticion}, "
            f"y el odontograma es {odontograma.denticion}",
        )
    return diente


def validar_hallazgo(
    db: Session,
    odontograma: Odontograma,
    *,
    codigo_fdi: int,
    superficie: str | None,
    condicion_dental_id: int,
) -> None:
    """Comprueba que el hallazgo tenga sentido sobre esa pieza.

    Las claves foráneas ya rechazan un diente o una cara inexistentes; aquí se
    verifica lo que ellas no ven: la dentición, el ámbito de la condición y que
    la cara exista realmente en ese diente.
    """
    diente = validar_pieza(db, odontograma, codigo_fdi)

    condicion = db.get(CondicionDental, condicion_dental_id)
    if condicion is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La condición dental no existe")

    if superficie is None:
        return

    # Una cara sólo puede llevar hallazgos de ámbito 'superficie'; lo demás
    # (ausencia, corona, implante) aplica al diente entero.
    if condicion.ambito != AmbitoCondicion.SUPERFICIE:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"'{condicion.nombre}' es de ámbito {condicion.ambito} y se registra "
            "sobre la pieza completa, sin superficie",
        )

    # Oclusal sólo en posteriores, incisal sólo en anteriores.
    if superficie == "O" and diente.grupo.es_anterior:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"La pieza {codigo_fdi} es un {diente.grupo} y no tiene cara oclusal; usa 'I'",
        )
    if superficie == "I" and not diente.grupo.es_anterior:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"La pieza {codigo_fdi} es un {diente.grupo} y no tiene cara incisal; usa 'O'",
        )
