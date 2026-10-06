"""Catálogos maestros que alimentan el odontograma, la ficha y la agenda.

Datos de solo lectura que no cambian durante una sesión: el frontend los pide
una vez y los cachea.
"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import BD, UsuarioAuth
from app.models.catalogo import Alergia, CondicionDental, CondicionMedica, Diente, Superficie
from app.models.enums import EstadoCita
from app.models.organizacion import Sede
from app.schemas.agenda import ClinicaLeer
from app.schemas.catalogo import AlergiaCatalogo, CondicionMedicaCatalogo, EstadoCitaLeer
from app.schemas.odontograma import (
    Catalogos,
    CondicionDentalLeer,
    DienteLeer,
    SuperficieLeer,
)

router = APIRouter(prefix="/catalogos", tags=["catálogos"])


@router.get("/odontograma", response_model=Catalogos)
def catalogos_odontograma(db: BD, _: UsuarioAuth) -> Catalogos:
    """Piezas, caras y condiciones en una sola llamada.

    Van juntas porque el odontograma no puede dibujarse sin las tres, y pedirlas
    por separado sólo añade viajes.
    """
    dientes = db.scalars(select(Diente).order_by(Diente.cuadrante, Diente.posicion)).all()
    superficies = db.scalars(select(Superficie).order_by(Superficie.codigo)).all()
    condiciones = db.scalars(
        select(CondicionDental).order_by(CondicionDental.orden, CondicionDental.codigo)
    ).all()

    return Catalogos(
        dientes=[DienteLeer.model_validate(d) for d in dientes],
        superficies=[SuperficieLeer.model_validate(s) for s in superficies],
        condiciones=[CondicionDentalLeer.model_validate(c) for c in condiciones],
    )


@router.get("/condiciones-medicas", response_model=list[CondicionMedicaCatalogo])
def condiciones_medicas(db: BD, _: UsuarioAuth) -> list[CondicionMedica]:
    """Antecedentes sistémicos, para el formulario de la ficha médica."""
    return list(db.scalars(select(CondicionMedica).order_by(CondicionMedica.nombre)))


@router.get("/alergias", response_model=list[AlergiaCatalogo])
def alergias(db: BD, _: UsuarioAuth) -> list[Alergia]:
    return list(db.scalars(select(Alergia).order_by(Alergia.nombre)))


# El color es dato, no decoración: la interfaz es acromática y estos son los
# únicos tonos que la agenda puede usar. Se eligen lejos de los rojos y azules
# saturados del catálogo dental y con contraste suficiente sobre blanco.
ESTADOS_CITA = [
    EstadoCitaLeer(valor=EstadoCita.AGENDADA, etiqueta="Pendiente", color_hex="#9A6700"),
    EstadoCitaLeer(valor=EstadoCita.CONFIRMADA, etiqueta="Confirmada", color_hex="#1F5FA8"),
    EstadoCitaLeer(valor=EstadoCita.EN_SALA, etiqueta="En sala", color_hex="#0F766E"),
    EstadoCitaLeer(valor=EstadoCita.ATENDIDA, etiqueta="Atendida", color_hex="#2F7D4F"),
    EstadoCitaLeer(valor=EstadoCita.CANCELADA, etiqueta="Cancelada", color_hex="#B42318"),
    EstadoCitaLeer(valor=EstadoCita.NO_ASISTIO, etiqueta="No asistió", color_hex="#5C6478"),
]


@router.get("/estados-cita", response_model=list[EstadoCitaLeer])
def estados_cita(_: UsuarioAuth) -> list[EstadoCitaLeer]:
    """Los seis estados de una cita, en el orden en que ocurren.

    `ocupa_agenda` coincide con el filtro de las restricciones de exclusión: una
    cita cancelada o a la que no se asistió libera al doctor y al sillón.
    """
    return [
        estado.model_copy(update={"ocupa_agenda": estado.valor.ocupa_agenda})
        for estado in ESTADOS_CITA
    ]


@router.get("/clinica", response_model=ClinicaLeer)
def clinica(db: BD, _: UsuarioAuth) -> Sede:
    """La sede principal: membrete de los impresos y firma de los mensajes."""
    sede = db.scalar(select(Sede).where(Sede.activo).order_by(Sede.id))
    if sede is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No hay ninguna sede registrada")
    return sede
