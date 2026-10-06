"""Modelos SQLAlchemy.

El esquema lo definen los .sql de `db/init/`; estos modelos lo mapean, no lo
generan. Cualquier cambio estructural se hace primero en el esquema (o, una vez
desplegado, en una migración de Alembic) y después aquí.
"""

from app.models.archivo import Archivo, DocumentoClinico
from app.models.base import Base
from app.models.catalogo import Alergia, CondicionDental, CondicionMedica, Diente, Superficie
from app.models.clinico import Cita, CitaEvento, Consulta
from app.models.cuenta import (
    CierreCaja,
    Factura,
    FacturaItem,
    Pago,
    PagoAplicacion,
    SecuenciaNcf,
)
from app.models.documento import (
    DocumentoEmitido,
    Firma,
    PlantillaDocumento,
    Prescripcion,
    PrescripcionItem,
)
from app.models.implante import Implante, ImplanteEvento, SistemaImplante
from app.models.inventario import (
    CategoriaGasto,
    CategoriaInsumo,
    Gasto,
    Insumo,
    MovimientoInsumo,
    Proveedor,
    ServicioInsumo,
)
from app.models.odontograma import Odontograma, OdontogramaDiente, OdontogramaHallazgo
from app.models.organizacion import (
    Correlativo,
    Doctor,
    DoctorEspecialidad,
    Especialidad,
    Sede,
    UnidadDental,
    Usuario,
)
from app.models.paciente import (
    FichaAlergia,
    FichaCondicion,
    FichaMedica,
    FichaMedicamento,
    Paciente,
    PacienteContacto,
)
from app.models.plan import PlanItem, PlanTratamiento, Procedimiento
from app.models.servicio import (
    Aseguradora,
    CategoriaServicio,
    ListaPrecio,
    PacienteSeguro,
    PrecioServicio,
    Servicio,
)

__all__ = [
    "Alergia",
    "Archivo",
    "DocumentoClinico",
    "CierreCaja",
    "SecuenciaNcf",
    "PacienteSeguro",
    "Implante",
    "ImplanteEvento",
    "SistemaImplante",
    "CategoriaGasto",
    "CategoriaInsumo",
    "DocumentoEmitido",
    "Firma",
    "Gasto",
    "Insumo",
    "MovimientoInsumo",
    "PlantillaDocumento",
    "Prescripcion",
    "PrescripcionItem",
    "Proveedor",
    "ServicioInsumo",
    "Aseguradora",
    "Base",
    "CategoriaServicio",
    "Cita",
    "CitaEvento",
    "CondicionDental",
    "CondicionMedica",
    "Consulta",
    "Correlativo",
    "Diente",
    "Doctor",
    "DoctorEspecialidad",
    "Especialidad",
    "Factura",
    "FacturaItem",
    "FichaAlergia",
    "FichaCondicion",
    "FichaMedica",
    "FichaMedicamento",
    "ListaPrecio",
    "Odontograma",
    "OdontogramaDiente",
    "OdontogramaHallazgo",
    "Paciente",
    "PacienteContacto",
    "Pago",
    "PagoAplicacion",
    "PlanItem",
    "PlanTratamiento",
    "PrecioServicio",
    "Procedimiento",
    "Sede",
    "Servicio",
    "Superficie",
    "UnidadDental",
    "Usuario",
]
