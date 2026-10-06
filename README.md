# DentalMaster · API

Backend de gestión clínica odontológica: pacientes, ficha médica, odontograma FDI,
catálogo de servicios, agenda, planes de tratamiento, procedimientos, implantes y
cuenta del paciente.

FastAPI · PostgreSQL 16 · SQLAlchemy 2 · Docker

## Arranque

```bash
cp .env.example .env
make up          # postgres + api + adminer, con datos demo
make verify      # 101 aserciones sobre la base → esperado 101 PASS / 0 FAIL
```

| Servicio | URL |
|---|---|
| API | http://localhost:8000 |
| Documentación (Swagger) | http://localhost:8000/docs |
| Adminer | http://localhost:8080 |

Usuarios demo — contraseña `dental2026` para todos:

| Email | Rol |
|---|---|
| `admin@dentalsonrisa.do` | admin |
| `laura.fernandez@dentalsonrisa.do` | doctor |
| `miguel.reyes@dentalsonrisa.do` | doctor |
| `carolina.batista@dentalsonrisa.do` | doctor |
| `recepcion@dentalsonrisa.do` | recepcion |

`make help` lista el resto de comandos.

## Despliegue

Servidor `74.208.173.175` (Ubuntu 24.04), junto a las APIs de GMD y TDI. Cada
proyecto vive en `~/projects/<nombre>`, escucha sólo en localhost y sale por
nginx con certificado Let's Encrypt.

| | API | Postgres |
|---|---|---|
| GMD | `:8000` | `:5433` |
| TDI | `:8001` | `:5434` |
| **DentalMaster** | **`:8002`** | **`:5435`** |

```bash
scripts/desplegar.sh                  # sube el código por rsync y reconstruye con Docker
scripts/desplegar.sh --simular        # enseña qué subiría, sin tocar nada
scripts/desplegar.sh --reiniciar-base # destruye base y almacén (pide escribir BORRAR)
```

El script sólo toca `~/projects/dentalmaster-api` y los contenedores de este proyecto, nunca
sube el `.env` (vive en el servidor) y no usa `docker-compose.override.yml`. Espera a que
`/health` responda en `:8002` y, si no lo hace, muestra los registros de la API. Se puede
apuntar a otro servidor con `SERVIDOR=` y `DESTINO=`. A mano sería:

```bash
ssh deploy@74.208.173.175
cd ~/projects/dentalmaster-api
docker compose -f docker-compose.prod.yml up -d --build
```

**`docker-compose.prod.yml` se invoca siempre de forma explícita.** Un
`docker compose up` a secas carga `docker-compose.override.yml`, que siembra los
cuatro pacientes de demo: en producción eso sería historia clínica falsa. El
archivo de producción es autónomo para que ese error no pueda ocurrir, y tampoco
levanta Adminer.

Primer arranque:

```bash
cp .env.produccion.example .env      # rellenar POSTGRES_PASSWORD y SECRET_KEY
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec api python -m app.cli crear-usuario \
    correo@clinica.do admin
```

`seed-users` no corre en producción, así que `crear-usuario` es la única vía de
entrada. Pide la contraseña por consola para que no quede en el historial.

Copia de seguridad — **la base y el almacén de archivos van juntos**. Las fotos, los
exámenes y los comprobantes viven en el volumen `archivos` (`/srv/almacen` en el contenedor);
la base sólo guarda su `sha256`:

```bash
docker exec dentalmaster-db pg_dump -U dental odonto > ~/dentalmaster_$(date +%Y%m%d).sql
docker run --rm -v dentalmasterapi_archivos:/almacen:ro -v ~:/copia alpine \
    tar czf /copia/dentalmaster_archivos_$(date +%Y%m%d).tgz -C /almacen .
```

El nombre del volumen lleva el prefijo del proyecto de Compose: `docker volume ls` lo
confirma. El tamaño máximo de un archivo es `ARCHIVO_MAX_MB` (25 por defecto); nginx debe
permitirlo con `client_max_body_size`.

## El esquema no lo genera Alembic

Los `.sql` de `db/` son la fuente de verdad del esquema inicial. Postgres los ejecuta por
orden alfabético desde `/docker-entrypoint-initdb.d`, y **sólo la primera vez** que el
volumen está vacío:

```
db/init/01_schema.sql          56 tablas, 13 ENUM, 6 vistas
db/init/02_seed_catalogos.sql  52 dientes FDI, 6 superficies, 35 condiciones, 47 servicios
db/dev/03_seed_demo.sql        datos de demo — sólo vía docker-compose.override.yml
db/99_verify.sql               101 aserciones de solo lectura (suite de regresión)
```

Al arrancar, la API ancla ese estado con `alembic stamp 0001_baseline` y a partir de ahí
aplica las migraciones incrementales.

**Mientras no haya un despliegue con datos reales, el esquema se cambia en los `.sql`**
(y en su copia canónica de `agent_info/`), ajustando las aserciones de `99_verify.sql`.
A partir del primer despliegue real, un cambio estructural se hace en una migración de
Alembic y se refleja después en los modelos — nunca editando los `.sql` del baseline.

`make verify` termina con error si alguna aserción falla **o si no se evaluaron las 101**:
el script activa `ON_ERROR_STOP` y cierra con una comprobación del total.

Para volver al estado inicial: `make reset` (destruye el volumen y reejecuta los tres `.sql`).

## Estructura

```
app/
├── core/       configuración, JWT y bcrypt, dependencias de FastAPI
├── db/         engine y sesiones
├── models/     SQLAlchemy — mapean el esquema, no lo generan
├── schemas/    Pydantic v2
├── api/v1/     routers
├── services/   reglas de negocio que el esquema no puede garantizar
└── cli.py      python -m app.cli {db-baseline,seed-users,crear-usuario,cambiar-password}
```

## Invariantes que vive el código, no la base

- **Un solo odontograma vigente por paciente.** Lo garantiza el índice parcial
  `uq_odontograma_actual`; el servicio crea la versión N+1 dentro de una transacción para
  no chocar contra él.
- **Los odontogramas históricos son inmutables.** Escribir sobre uno con `es_actual=FALSE`
  devuelve `409`. Esa restricción no existe en el esquema: es del servicio.
- **`plan_item.total` es columna generada.** Nunca se inserta ni se actualiza.
- **`superficie IS NULL` significa "toda la pieza"**, no un dato faltante. Distingue un
  hallazgo de pieza completa (ausente, corona, implante) de uno de cara concreta.
- **El dinero cuelga del paciente.** El cargo es `procedimiento.total` (columna generada);
  el pago es del paciente y se imputa a consultas en `pago_aplicacion`. `v_estado_cuenta`
  (por paciente) y `v_saldo_consulta` salen de los mismos datos y deben conciliar. La
  factura es el comprobante fiscal opcional: no recibe pagos.
- **Un pago no se borra ni cambia de monto: se anula.** Conserva su número de recibo y sale
  de todo balance.
- **Los números salen de `services/correlativos.py`**, nunca de un `max()+1`: avanza la
  fila de `correlativo` dentro de la transacción, así dos altas simultáneas no chocan y un
  rollback no deja huecos.
- **El servidor corre en UTC; la clínica, no.** «Hoy» y las horas mostradas salen de
  `app/core/tiempo.py`, nunca de `date.today()`.
- **Un documento emitido es inmutable** y lleva su `sha256`; la firma guarda el trazo y ese
  hash. Se firma por un enlace sin sesión que sólo abre ese documento.
- **La existencia de un insumo es la suma de su kárdex.** Ejecutar un servicio descuenta su
  receta; quitar la línea lo devuelve con otro asiento.
- **Las citas no se solapan.** Lo impiden `ex_cita_doctor` y `ex_cita_unidad` en la base;
  `app/main.py` traduce la violación a un 409. Solapar a propósito exige `sobrecupo` con
  motivo.
- **Buscar es sin tildes.** `services/busqueda.py` usa la extensión `unaccent`: «gomez» encuentra
  «Gómez», y un teléfono se encuentra por sus dígitos. No se escribe un `ilike` suelto.
- **Los teléfonos se guardan como `(809) 555-0100`** (`core/telefono.py`); lo que no tenga diez
  dígitos se rechaza con 422.
- **Los datos de la clínica son la sede principal** y los edita sólo administración
  (`PATCH /catalogos/clinica`, `PUT|DELETE /catalogos/clinica/logo`).
- **Los precios salen de `precio_servicio`**, resolviendo por lista y vigencia — nunca de
  `servicio`.
- **El tipo de un archivo lo deciden sus bytes** (`services/almacen.py`): JPG, PNG, WebP o
  PDF; lo demás es 415. Se guarda por `sha256` y se sirve sólo con sesión.
- **Un NCF no se repite ni se salta.** `emitir_factura` toma la secuencia activa con
  `FOR UPDATE`; una línea ejecutada no entra en dos comprobantes vivos. La factura se anula
  con motivo y su número no se reutiliza.
- **Lo planificado sigue al plan.** Un ítem con pieza pinta su condición como `planificado`
  y la mantiene: editarlo la mueve, quitarlo la retira, ejecutarlo la completa.
- **Un implante registrado ata su línea**: no se puede quitar de la consulta, porque el lote
  es lo que responde a un retiro de producto.

## Notas de dependencias

Se usan `bcrypt` y `PyJWT` directamente. `passlib` está sin mantenimiento desde 2020 y
necesita un parche para bcrypt 4.x; `python-jose` aborta con SIGILL en aarch64.
