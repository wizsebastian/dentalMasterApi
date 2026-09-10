# DentalMaster · API

Backend de gestión clínica odontológica: pacientes, ficha médica, odontograma FDI,
planes de tratamiento, procedimientos, implantes y facturación.

FastAPI · PostgreSQL 16 · SQLAlchemy 2 · Docker

## Arranque

```bash
cp .env.example .env
make up          # postgres + api + adminer, con datos demo
make verify      # 79 aserciones sobre la base → esperado 79 PASS / 0 FAIL
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
ssh deploy@74.208.173.175
cd ~/projects/dentalmaster-api
git pull
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

Copia de seguridad:

```bash
docker exec dentalmaster-db pg_dump -U dental odonto > ~/dentalmaster_$(date +%Y%m%d).sql
```

## El esquema no lo genera Alembic

Los `.sql` de `db/` son la fuente de verdad del esquema inicial. Postgres los ejecuta por
orden alfabético desde `/docker-entrypoint-initdb.d`, y **sólo la primera vez** que el
volumen está vacío:

```
db/init/01_schema.sql          40 tablas, 13 ENUM, 3 vistas
db/init/02_seed_catalogos.sql  52 dientes FDI, 6 superficies, 35 condiciones, 47 servicios
db/dev/03_seed_demo.sql        datos de demo — sólo vía docker-compose.override.yml
db/99_verify.sql               79 aserciones de solo lectura (suite de regresión)
```

Al arrancar, la API ancla ese estado con `alembic stamp 0001_baseline` y a partir de ahí
aplica las migraciones incrementales. Un cambio estructural se hace en una migración de
Alembic y se refleja después en los modelos — nunca al revés, y nunca editando los `.sql`
del baseline.

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
└── cli.py      python -m app.cli {db-baseline,seed-users}
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
- **`factura.estado` no lo mantiene la base.** El servicio de pagos lo recalcula tras cada
  cobro; si no, la aserción "ninguna factura pagada con saldo" empieza a fallar.
- **Los precios salen de `precio_servicio`**, resolviendo por lista y vigencia — nunca de
  `servicio`.

## Notas de dependencias

Se usan `bcrypt` y `PyJWT` directamente. `passlib` está sin mantenimiento desde 2020 y
necesita un parche para bcrypt 4.x; `python-jose` aborta con SIGILL en aarch64.
