"""Plantillas con variables, documentos inmutables y cruce de alergias."""

import hashlib
import re
import unicodedata
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tiempo import hoy, local
from app.models.catalogo import Alergia
from app.models.clinico import Consulta
from app.models.organizacion import Doctor, Sede
from app.models.paciente import FichaAlergia, FichaMedica, Paciente
from app.models.plan import PlanTratamiento

_VARIABLE = re.compile(r"\{\{\s*([a-z_.]+)\s*\}\}")

_MESES = (
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre"
).split()


def fecha_en_letras(dia: date) -> str:
    return f"{dia.day} de {_MESES[dia.month - 1]} de {dia.year}"


def sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def contexto(
    db: Session,
    paciente: Paciente,
    *,
    consulta: Consulta | None = None,
    plan: PlanTratamiento | None = None,
    doctor: Doctor | None = None,
) -> dict[str, str]:
    """Los datos que una plantilla puede pedir. La lista es cerrada.

    Sin consulta indicada se toma la última del paciente: una constancia suele
    pedirse por la visita que acaba de terminar.
    """
    if consulta is None:
        consulta = db.scalar(
            select(Consulta)
            .where(Consulta.paciente_id == paciente.id)
            .order_by(Consulta.fecha.desc())
            .limit(1)
        )
    if doctor is None:
        doctor = (
            consulta.doctor if consulta else (plan.doctor if plan else paciente.doctor_tratante)
        )
    clinica = db.scalar(select(Sede).where(Sede.activo).order_by(Sede.id))

    datos: dict[str, str | None] = {
        "paciente.nombre": paciente.nombre_completo,
        "paciente.documento": paciente.documento,
        "paciente.edad": str(paciente.edad) if paciente.edad is not None else None,
        "paciente.telefono": paciente.celular or paciente.telefono,
        "doctor.nombre": f"Dr(a). {doctor.nombre_completo}" if doctor else None,
        "doctor.licencia": doctor.licencia if doctor else None,
        "clinica.nombre": clinica.nombre if clinica else None,
        "clinica.ciudad": clinica.ciudad if clinica else None,
        "clinica.telefono": clinica.telefono if clinica else None,
        "clinica.whatsapp": clinica.whatsapp if clinica else None,
        "clinica.correo": clinica.email if clinica else None,
        "clinica.web": clinica.web if clinica else None,
        "fecha": fecha_en_letras(hoy()),
        "consulta.fecha": fecha_en_letras(local(consulta.fecha).date()) if consulta else None,
        "consulta.servicios": (
            ", ".join(linea.servicio.nombre for linea in consulta.lineas) or None
            if consulta
            else None
        ),
        "plan.codigo": plan.codigo if plan else None,
        "plan.titulo": (plan.titulo or plan.especialidad_nombre or plan.codigo) if plan else None,
    }
    # Lo que falta se imprime visible, para que quien revisa lo complete antes de emitir.
    return {clave: valor or f"[{clave.replace('.', ': ')}]" for clave, valor in datos.items()}


def combinar(cuerpo: str, datos: dict[str, str]) -> str:
    """Sustituye las variables conocidas; una desconocida se deja a la vista."""
    return _VARIABLE.sub(lambda m: datos.get(m.group(1), f"[{m.group(1)}]"), cuerpo)


def variables_desconocidas(cuerpo: str) -> list[str]:
    conocidas = set(contexto_vacio())
    return sorted({v for v in _VARIABLE.findall(cuerpo) if v not in conocidas})


def contexto_vacio() -> dict[str, str]:
    return dict.fromkeys(
        [
            "paciente.nombre",
            "paciente.documento",
            "paciente.edad",
            "paciente.telefono",
            "doctor.nombre",
            "doctor.licencia",
            "clinica.nombre",
            "clinica.ciudad",
            "clinica.telefono",
            "clinica.whatsapp",
            "clinica.correo",
            "clinica.web",
            "fecha",
            "consulta.fecha",
            "consulta.servicios",
            "plan.codigo",
            "plan.titulo",
        ],
        "",
    )


def validar_plantilla(cuerpo: str) -> None:
    """Una variable que el sistema no conoce se rechaza al guardar, no al emitir."""
    desconocidas = variables_desconocidas(cuerpo)
    if desconocidas:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "cuerpo: variables que no existen: " + ", ".join(f"{{{{{v}}}}}" for v in desconocidas),
        )


# --- Alergias ------------------------------------------------------------------


def _plano(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower()


def choques_con_alergias(db: Session, paciente_id: int, medicamentos: list[str]) -> list[str]:
    """Medicamentos de la receta que chocan con una alergia registrada del paciente.

    Compara contra las palabras clave del catálogo (`alergia.palabras_clave`):
    quien es alérgico a la penicilina lo es a la amoxicilina, aunque los nombres
    no se parezcan.
    """
    alergias = db.scalars(
        select(Alergia)
        .join(FichaAlergia, FichaAlergia.alergia_id == Alergia.id)
        .join(FichaMedica, FichaMedica.id == FichaAlergia.ficha_id)
        .where(FichaMedica.paciente_id == paciente_id)
    ).all()

    avisos = []
    for medicamento in medicamentos:
        texto = _plano(medicamento)
        for alergia in alergias:
            if any(_plano(clave) in texto for clave in alergia.palabras_clave):
                avisos.append(f"«{medicamento}» choca con la alergia a {alergia.nombre}")
    return avisos
