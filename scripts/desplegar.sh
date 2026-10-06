#!/usr/bin/env bash
# Sube la API al VPS y la levanta con Docker (docker-compose.prod.yml).
#
#   scripts/desplegar.sh                    # sube el código y reconstruye
#   scripts/desplegar.sh --simular          # muestra qué subiría, sin tocar nada
#   scripts/desplegar.sh --reiniciar-base   # DESTRUYE la base y el almacén (pide confirmación)
#
# Variables opcionales:
#   SERVIDOR=deploy@74.208.173.175   DESTINO=projects/dentalmaster-api
#
# El servidor se comparte con las APIs de GMD y TDI: este script sólo toca
# ~/$DESTINO y los contenedores de este proyecto. El `.env` de producción vive en
# el servidor y NUNCA se sube desde aquí.
set -euo pipefail

SERVIDOR="${SERVIDOR:-deploy@74.208.173.175}"
DESTINO="${DESTINO:-projects/dentalmaster-api}"
PUERTO_API=8002
COMPOSE="docker compose -f docker-compose.prod.yml"

SIMULAR=0
REINICIAR=0
for arg in "$@"; do
  case "$arg" in
    --simular) SIMULAR=1 ;;
    --reiniciar-base) REINICIAR=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $arg" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."
[ -f docker-compose.prod.yml ] || { echo "Ejecútalo desde dentalMasterApi/." >&2; exit 1; }

paso() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
remoto() { ssh -o BatchMode=yes "$SERVIDOR" "$@"; }

paso "Comprobando acceso a $SERVIDOR"
remoto "docker compose version" >/dev/null \
  || { echo "No hay acceso por SSH o Docker no está disponible en el servidor." >&2; exit 1; }

paso "Preparando ~/$DESTINO"
remoto "mkdir -p ~/$DESTINO"

if ! remoto "test -s ~/$DESTINO/.env"; then
  echo "Falta ~/$DESTINO/.env en el servidor. Primer arranque:" >&2
  echo "  1. $0 --simular   (o sube el código una vez)" >&2
  echo "  2. ssh $SERVIDOR 'cd ~/$DESTINO && cp .env.produccion.example .env && nano .env'" >&2
  echo "     (rellena POSTGRES_PASSWORD con 'openssl rand -base64 24' y SECRET_KEY con 'openssl rand -hex 32')" >&2
  if [ "$SIMULAR" -eq 0 ]; then
    echo "Subiendo el código para que puedas crearlo…" >&2
    rsync -az --exclude-from=- ./ "$SERVIDOR:~/$DESTINO/" <<'LISTA'
.git/
.env
.venv/
venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
verificacion.txt
docker-compose.override.yml
LISTA
  fi
  exit 1
fi

paso "Subiendo el código (rsync)"
OPCIONES=(-az --delete --itemize-changes)
[ "$SIMULAR" -eq 1 ] && OPCIONES+=(--dry-run)
rsync "${OPCIONES[@]}" \
  --exclude '.git/' --exclude '.env' --exclude '.venv/' --exclude 'venv/' \
  --exclude '__pycache__/' --exclude '*.pyc' --exclude '.pytest_cache/' \
  --exclude '.ruff_cache/' --exclude 'verificacion.txt' \
  --exclude 'docker-compose.override.yml' \
  ./ "$SERVIDOR:~/$DESTINO/"

if [ "$SIMULAR" -eq 1 ]; then
  echo; echo "Simulación: no se subió nada ni se tocó Docker."
  exit 0
fi

if remoto "docker volume ls -q | grep -q 'pgdata'" && [ "$REINICIAR" -eq 0 ]; then
  echo
  echo "Aviso: ya existe un volumen de base. Postgres sólo aplica los .sql de db/init/ la"
  echo "primera vez; un cambio de esquema NO se aplica solo (hace falta una migración de"
  echo "Alembic o --reiniciar-base, que borra los datos)."
fi

if [ "$REINICIAR" -eq 1 ]; then
  echo
  echo "Esto BORRA la base y el almacén de archivos (fotos, exámenes, comprobantes) de DentalMaster en $SERVIDOR."
  read -r -p "Escribe BORRAR para continuar: " confirmacion
  [ "$confirmacion" = "BORRAR" ] || { echo "Cancelado."; exit 1; }
  paso "Destruyendo contenedores y volúmenes de este proyecto"
  remoto "cd ~/$DESTINO && $COMPOSE down -v"
fi

paso "Construyendo y levantando con Docker"
remoto "cd ~/$DESTINO && $COMPOSE up -d --build"

paso "Esperando a que la API responda en :$PUERTO_API"
for _ in $(seq 1 40); do
  if remoto "curl -fsS http://127.0.0.1:$PUERTO_API/health" >/dev/null 2>&1; then
    remoto "cd ~/$DESTINO && $COMPOSE ps"
    echo
    echo "Listo: la API responde. Si es el primer arranque, crea el administrador:"
    echo "  ssh -t $SERVIDOR 'cd ~/$DESTINO && $COMPOSE exec api python -m app.cli iniciar-clinica correo@clinica.do \"Nombre de la clínica\"'"
    exit 0
  fi
  sleep 3
done

echo "La API no respondió a tiempo. Últimos registros:" >&2
remoto "cd ~/$DESTINO && $COMPOSE logs --tail=60 api" >&2
exit 1
