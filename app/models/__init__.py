"""Modelos SQLAlchemy.

El esquema lo definen los .sql de `db/init/`; estos modelos lo mapean, no lo
generan. Cualquier cambio estructural se hace primero en una migración de
Alembic y después aquí.
"""

from app.models.base import Base
from app.models.catalogo import Alergia, CondicionDental, CondicionMedica, Diente, Superficie
from app.models.clinico import Cita, Consulta
from app.models.odontograma import Odontograma, OdontogramaDiente, OdontogramaHallazgo
from app.models.organizacion import Doctor, DoctorEspecialidad, Especialidad, Sede, Usuario
from app.models.paciente import (
    FichaAlergia,
    FichaCondicion,
    FichaMedica,
    FichaMedicamento,
    Paciente,
    PacienteContacto,
)

__all__ = [
    "Alergia",
    "Base",
    "Cita",
    "CondicionDental",
    "CondicionMedica",
    "Consulta",
    "Diente",
    "Doctor",
    "DoctorEspecialidad",
    "Especialidad",
    "FichaAlergia",
    "FichaCondicion",
    "FichaMedica",
    "FichaMedicamento",
    "Odontograma",
    "OdontogramaDiente",
    "OdontogramaHallazgo",
    "Paciente",
    "PacienteContacto",
    "Sede",
    "Superficie",
    "Usuario",
]
