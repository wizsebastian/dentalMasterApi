"""Catálogo de servicios, sus categorías y las listas de precio.

Lo lee cualquiera con sesión —lo usan la agenda, los planes y las consultas—;
lo edita sólo administración, porque un precio cambiado afecta a toda la clínica.
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import BD, UsuarioAuth, requiere_rol
from app.core.tiempo import hoy
from app.models.organizacion import Usuario
from app.models.servicio import (
    Aseguradora,
    CategoriaServicio,
    ListaPrecio,
    PrecioServicio,
    Servicio,
)
from app.schemas.catalogo import (
    AseguradoraLeer,
    CategoriaActualizar,
    CategoriaCrear,
    CategoriaLeer,
    ListaPrecioActualizar,
    ListaPrecioCrear,
    ListaPrecioLeer,
    ServicioActualizar,
    ServicioCrear,
    ServicioLeer,
)
from app.services import catalogo as servicio_catalogo
from app.services import correlativos
from app.services.busqueda import coincide

router = APIRouter(tags=["catálogo de servicios"])

SoloAdmin = Annotated[Usuario, Depends(requiere_rol())]


# --- Listas de precio ----------------------------------------------------------


@router.get("/listas-precio", response_model=list[ListaPrecioLeer])
def listar_listas(db: BD, _: UsuarioAuth) -> list[ListaPrecio]:
    """Las tarifas activas. La primera es siempre la particular."""
    return list(
        db.scalars(
            select(ListaPrecio)
            .where(ListaPrecio.activo)
            .order_by(ListaPrecio.aseguradora_id.is_not(None), ListaPrecio.id)
        )
    )


@router.get("/aseguradoras", response_model=list[AseguradoraLeer])
def listar_aseguradoras(db: BD, _: UsuarioAuth) -> list[Aseguradora]:
    """Las ARS. «Particular» no es una aseguradora: es no tener ninguna."""
    return list(
        db.scalars(
            select(Aseguradora)
            .where(Aseguradora.activo, Aseguradora.codigo != "PARTIC")
            .order_by(Aseguradora.nombre)
        )
    )


@router.post("/listas-precio", response_model=ListaPrecioLeer, status_code=status.HTTP_201_CREATED)
def crear_lista(datos: ListaPrecioCrear, db: BD, _: SoloAdmin) -> ListaPrecio:
    """Crea una tarifa copiando los precios de otra: ningún servicio queda sin precio."""
    nombre = datos.nombre.strip()
    if db.scalar(select(ListaPrecio.id).where(func.lower(ListaPrecio.nombre) == nombre.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe una tarifa «{nombre}»")
    if datos.aseguradora_id is not None and db.get(Aseguradora, datos.aseguradora_id) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "aseguradora_id: la aseguradora no existe"
        )

    origen = (
        db.get(ListaPrecio, datos.copiar_de)
        if datos.copiar_de is not None
        else servicio_catalogo.lista_particular(db)
    )
    if origen is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "copiar_de: la tarifa de origen no existe"
        )

    lista = ListaPrecio(
        codigo=servicio_catalogo.codigo_desde_nombre(db, ListaPrecio, nombre),
        nombre=nombre,
        aseguradora_id=datos.aseguradora_id,
        vigente_desde=hoy(),
    )
    db.add(lista)
    db.flush()

    factor = 1 + datos.ajuste_pct / 100
    for precio in db.scalars(
        select(PrecioServicio).where(PrecioServicio.lista_precio_id == origen.id)
    ):
        db.add(
            PrecioServicio(
                lista_precio_id=lista.id,
                servicio_id=precio.servicio_id,
                precio=(precio.precio * factor).quantize(Decimal("0.01")),
                costo=precio.costo,
                cobertura_pct=datos.cobertura_pct,
                tasa_impuesto=precio.tasa_impuesto,
            )
        )
    db.commit()
    db.refresh(lista)
    return lista


@router.patch("/listas-precio/{lista_id}", response_model=ListaPrecioLeer)
def actualizar_lista(
    lista_id: int, datos: ListaPrecioActualizar, db: BD, _: SoloAdmin
) -> ListaPrecio:
    lista = db.get(ListaPrecio, lista_id)
    if lista is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La tarifa no existe")
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("activo") is False and lista.id == servicio_catalogo.lista_particular(db).id:
        raise HTTPException(status.HTTP_409_CONFLICT, "La tarifa particular no se puede desactivar")
    for campo, valor in cambios.items():
        if valor is not None:
            setattr(lista, campo, valor.strip() if isinstance(valor, str) else valor)
    db.commit()
    db.refresh(lista)
    return lista


# --- Categorías ----------------------------------------------------------------


def _categoria(db: Session, categoria_id: int) -> CategoriaServicio:
    categoria = db.get(CategoriaServicio, categoria_id)
    if categoria is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La categoría no existe")
    return categoria


def _exigir_nombre_libre(db: Session, nombre: str, excepto: int | None = None) -> None:
    """Las categorías son un catálogo, no texto libre: sin esto acaban conviviendo
    «Periodoncia» y «Periodontales»."""
    duplicada = db.scalar(
        select(CategoriaServicio.id).where(
            func.lower(CategoriaServicio.nombre) == nombre.strip().lower(),
            CategoriaServicio.id != (excepto or 0),
        )
    )
    if duplicada is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe la categoría «{nombre}»")


def _categoria_leer(categoria: CategoriaServicio, servicios: int) -> CategoriaLeer:
    return CategoriaLeer.model_validate(categoria).model_copy(update={"servicios": servicios})


@router.get("/categorias-servicio", response_model=list[CategoriaLeer])
def listar_categorias(db: BD, _: UsuarioAuth) -> list[CategoriaLeer]:
    conteo = dict(
        db.execute(
            select(Servicio.categoria_id, func.count()).group_by(Servicio.categoria_id)
        ).all()
    )
    categorias = db.scalars(
        select(CategoriaServicio).order_by(CategoriaServicio.orden, CategoriaServicio.nombre)
    )
    return [_categoria_leer(c, conteo.get(c.id, 0)) for c in categorias]


@router.post(
    "/categorias-servicio", response_model=CategoriaLeer, status_code=status.HTTP_201_CREATED
)
def crear_categoria(datos: CategoriaCrear, db: BD, _: SoloAdmin) -> CategoriaLeer:
    _exigir_nombre_libre(db, datos.nombre)
    if datos.codigo and db.scalar(
        select(CategoriaServicio.id).where(CategoriaServicio.codigo == datos.codigo)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe el código {datos.codigo}")

    orden = datos.orden
    if orden is None:
        orden = (db.scalar(select(func.max(CategoriaServicio.orden))) or 0) + 1

    categoria = CategoriaServicio(
        nombre=datos.nombre.strip(),
        codigo=datos.codigo
        or servicio_catalogo.codigo_desde_nombre(db, CategoriaServicio, datos.nombre),
        orden=orden,
    )
    db.add(categoria)
    db.commit()
    db.refresh(categoria)
    return _categoria_leer(categoria, 0)


@router.patch("/categorias-servicio/{categoria_id}", response_model=CategoriaLeer)
def actualizar_categoria(
    categoria_id: int, datos: CategoriaActualizar, db: BD, _: SoloAdmin
) -> CategoriaLeer:
    categoria = _categoria(db, categoria_id)
    cambios = datos.model_dump(exclude_unset=True)

    if cambios.get("nombre"):
        _exigir_nombre_libre(db, cambios["nombre"], excepto=categoria_id)
        categoria.nombre = cambios["nombre"].strip()
    if "orden" in cambios and cambios["orden"] is not None:
        categoria.orden = cambios["orden"]

    db.commit()
    db.refresh(categoria)
    servicios = db.scalar(
        select(func.count()).select_from(Servicio).where(Servicio.categoria_id == categoria_id)
    )
    return _categoria_leer(categoria, servicios or 0)


@router.delete("/categorias-servicio/{categoria_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_categoria(categoria_id: int, db: BD, _: SoloAdmin) -> None:
    categoria = _categoria(db, categoria_id)
    servicios = db.scalar(
        select(func.count()).select_from(Servicio).where(Servicio.categoria_id == categoria_id)
    )
    if servicios:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"La categoría tiene {servicios} servicio(s): muévelos a otra antes de borrarla",
        )
    db.delete(categoria)
    db.commit()


# --- Servicios -----------------------------------------------------------------


def _servicio(db: Session, servicio_id: int) -> Servicio:
    servicio = db.scalar(
        select(Servicio).where(Servicio.id == servicio_id).options(selectinload(Servicio.precios))
    )
    if servicio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El servicio no existe")
    return servicio


def _servicio_leer(servicio: Servicio, en_uso: bool) -> ServicioLeer:
    return ServicioLeer.model_validate(servicio).model_copy(update={"en_uso": en_uso})


@router.get("/servicios", response_model=list[ServicioLeer])
def listar_servicios(
    db: BD,
    _: UsuarioAuth,
    buscar: str | None = Query(default=None, description="Nombre, código o categoría"),
    categoria_id: int | None = None,
    incluir_inactivos: bool = False,
) -> list[ServicioLeer]:
    """El catálogo completo, sin paginar: son decenas de filas y la interfaz
    filtra sobre ellas mientras se escribe."""
    consulta = (
        select(Servicio)
        .join(Servicio.categoria)
        .options(selectinload(Servicio.precios))
        .order_by(CategoriaServicio.orden, CategoriaServicio.nombre, func.lower(Servicio.nombre))
    )
    if not incluir_inactivos:
        consulta = consulta.where(Servicio.activo)
    if categoria_id is not None:
        consulta = consulta.where(Servicio.categoria_id == categoria_id)
    if buscar:
        consulta = consulta.where(
            or_(
                coincide(Servicio.nombre, buscar),
                coincide(Servicio.codigo, buscar),
                coincide(CategoriaServicio.nombre, buscar),
            )
        )

    en_uso = servicio_catalogo.servicios_en_uso(db)
    return [_servicio_leer(s, s.id in en_uso) for s in db.scalars(consulta)]


@router.get("/servicios/{servicio_id}", response_model=ServicioLeer)
def obtener_servicio(servicio_id: int, db: BD, _: UsuarioAuth) -> ServicioLeer:
    servicio = _servicio(db, servicio_id)
    return _servicio_leer(servicio, servicio.id in servicio_catalogo.servicios_en_uso(db))


@router.post("/servicios", response_model=ServicioLeer, status_code=status.HTTP_201_CREATED)
def crear_servicio(datos: ServicioCrear, db: BD, _: SoloAdmin) -> ServicioLeer:
    categoria = servicio_catalogo.exigir_categoria(db, datos.categoria_id)
    servicio_catalogo.validar_condicion_resultante(db, datos.condicion_resultante_id)

    servicio = Servicio(
        **datos.model_dump(exclude={"precios"}),
        codigo=correlativos.codigo_servicio(db, categoria.codigo),
        activo=True,
    )
    servicio_catalogo.guardar_precios(db, servicio, datos.precios)
    servicio_catalogo.exigir_precio_particular(db, servicio)

    db.add(servicio)
    db.commit()
    return _servicio_leer(_servicio(db, servicio.id), en_uso=False)


@router.patch("/servicios/{servicio_id}", response_model=ServicioLeer)
def actualizar_servicio(
    servicio_id: int, datos: ServicioActualizar, db: BD, _: SoloAdmin
) -> ServicioLeer:
    servicio = _servicio(db, servicio_id)
    cambios = datos.model_dump(exclude_unset=True, exclude={"precios"})

    if cambios.get("categoria_id") is not None:
        servicio_catalogo.exigir_categoria(db, cambios["categoria_id"])
    if "condicion_resultante_id" in cambios:
        servicio_catalogo.validar_condicion_resultante(db, cambios["condicion_resultante_id"])

    # Sólo estos dos pueden quedar en NULL; el resto son NOT NULL en el esquema.
    anulables = {"descripcion", "condicion_resultante_id"}
    for campo, valor in cambios.items():
        if valor is None and campo not in anulables:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"{campo}: no puede quedar vacío"
            )
        setattr(servicio, campo, valor)

    if datos.precios is not None:
        servicio_catalogo.guardar_precios(db, servicio, datos.precios)

    db.commit()
    servicio = _servicio(db, servicio_id)
    return _servicio_leer(servicio, servicio.id in servicio_catalogo.servicios_en_uso(db))


@router.delete("/servicios/{servicio_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_servicio(servicio_id: int, db: BD, _: SoloAdmin) -> None:
    servicio = _servicio(db, servicio_id)
    if servicio.id in servicio_catalogo.servicios_en_uso(db):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "El servicio ya aparece en citas, planes o procedimientos: desactívalo en lugar "
            "de borrarlo",
        )
    db.delete(servicio)
    db.commit()
