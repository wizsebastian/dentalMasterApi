#!/usr/bin/env bash
# Prepara la base antes de arrancar la API.
#
# El esquema NO lo crea Alembic: lo crean los .sql de db/init vía initdb.d de
# Postgres. Alembic sólo toma ese estado como baseline (`stamp`) y a partir de
# ahí gestiona los cambios incrementales.
set -euo pipefail

echo "[entrypoint] esperando a la base..."
until python -c "
import os, sys
import psycopg
url = os.environ['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://')
try:
    psycopg.connect(url, connect_timeout=3).close()
except Exception as exc:
    print(exc, file=sys.stderr); sys.exit(1)
" 2>/dev/null; do
  sleep 1
done
echo "[entrypoint] base disponible"

python -m app.cli db-baseline

if [ "${SEED_DEMO_USERS:-false}" = "true" ]; then
  python -m app.cli seed-users
fi

exec "$@"
