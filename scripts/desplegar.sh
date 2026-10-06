#!/usr/bin/env bash
# Sube la API al VPS por rsync (nunca por GitHub) y la levanta con Docker
# (docker-compose.prod.yml). En el primer arranque genera el .env del
# servidor y da de alta a los dos administradores.
#
#   scripts/desplegar.sh                    # sube el código y reconstruye
#   scripts/desplegar.sh --simular          # muestra qué subiría, sin tocar nada
#   scripts/desplegar.sh --reiniciar-base   # DESTRUYE la base y el almacén (pide confirmación)
#
# Variables opcionales:
#   SERVIDOR=deploy@74.208.173.175   DESTINO=projects/dentalmaster-api
#
# El servidor se comparte con las APIs de GMD y TDI: este script sólo toca
# ~/$DESTINO y los contenedores de este proyecto.
set -euo pipefail

SERVIDOR="${SERVIDOR:-deploy@74.208.173.175}"
DESTINO="${DESTINO:-projects/dentalmaster-api}"
PUERTO_API=8002
COMPOSE="docker compose -f docker-compose.prod.yml"

# Los dos administradores que se dan de alta en el primer arranque. Ambos son
# usuarios normales: visibles en `usuario`, con su propio rastro de sesión
# como cualquier cuenta de la clínica. El segundo es de uso del equipo técnico
# para mantenimiento, no de la clínica — se distingue por el correo, no está
# oculto.
ADMIN_CLINICA="admin@drgabrielmartinez.com"
ADMIN_MANTENIMIENTO="wizsebastian@gmail.com"

SIMULAR=0
REINICIAR=0
for arg in "$@"; do
  case "$arg" in
    --simular) SIMULAR=1 ;;
    --reiniciar-base) REINICIAR=1 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $arg" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."
[ -f docker-compose.prod.yml ] || { echo "Ejecútalo desde dentalMasterApi/." >&2; exit 1; }

paso() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
# -n: no leer la entrada estándar del script (si no, un `ssh` de paso se come
# la confirmación «BORRAR» antes de que llegue al `read`). El único comando que
# sí necesita entrada (crear-usuario, para la contraseña) usa `remoto_con_entrada`.
remoto() { ssh -o BatchMode=yes -n "$SERVIDOR" "$@"; }
remoto_con_entrada() { ssh -o BatchMode=yes "$SERVIDOR" "$@"; }

paso "Comprobando acceso a $SERVIDOR"
remoto "docker compose version" >/dev/null \
  || { echo "No hay acceso por SSH o Docker no está disponible en el servidor." >&2; exit 1; }

paso "Preparando ~/$DESTINO"
remoto "mkdir -p ~/$DESTINO"

paso "Subiendo el código (rsync, sin pasar por git)"
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

# Este Mac trae `openrsync`, no GNU rsync: --chmod no tiene efecto ahí y deja
# algunos archivos en 600 (umask heredado). Sin este arreglo llegan ilegibles
# para el usuario de Postgres dentro del contenedor, y db/init/*.sql falla en
# silencio con «Permission denied» sin crear ninguna tabla. Nunca toca .env.
paso "Corrigiendo permisos en el servidor"
remoto "find ~/$DESTINO -type d -exec chmod u+rwx,go+rx-w {} + \
  && find ~/$DESTINO -type f ! -name .env -exec chmod u+rw,go+r-w {} +"

PRIMER_ARRANQUE=0
if ! remoto "test -s ~/$DESTINO/.env"; then
  PRIMER_ARRANQUE=1
  paso "Generando ~/$DESTINO/.env en el servidor"
  PG_PASS=$(remoto "openssl rand -base64 24")
  SECRET=$(remoto "openssl rand -hex 32")
  remoto "cat > ~/$DESTINO/.env" <<EOF
POSTGRES_PASSWORD=$PG_PASS
SECRET_KEY=$SECRET
CORS_ORIGINS=https://dentalmaster.wizsebastian.com
DEBUG=false
SEED_DEMO_USERS=false
EOF
  remoto "chmod 600 ~/$DESTINO/.env"
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
  PRIMER_ARRANQUE=1
fi

paso "Construyendo y levantando con Docker"
remoto "cd ~/$DESTINO && $COMPOSE up -d --build"

paso "Esperando a que la API responda en :$PUERTO_API"
LISTA=0
for _ in $(seq 1 40); do
  if remoto "curl -fsS http://127.0.0.1:$PUERTO_API/health" >/dev/null 2>&1; then
    LISTA=1
    break
  fi
  sleep 3
done

if [ "$LISTA" -ne 1 ]; then
  echo "La API no respondió a tiempo. Últimos registros:" >&2
  remoto "cd ~/$DESTINO && $COMPOSE logs --tail=60 api" >&2
  exit 1
fi

remoto "cd ~/$DESTINO && $COMPOSE ps"

if [ "$PRIMER_ARRANQUE" -eq 1 ]; then
  paso "Dando de alta a los dos administradores"
  PASS_CLINICA=$(remoto "openssl rand -base64 18")
  PASS_MANTENIMIENTO=$(remoto "openssl rand -base64 18")

  remoto "cd ~/$DESTINO && $COMPOSE exec -T -e PASSWORD_INICIAL='$PASS_CLINICA' api \
    python -m app.cli iniciar-clinica '$ADMIN_CLINICA' 'Dr. Gabriel Martínez'"

  remoto_con_entrada "cd ~/$DESTINO && $COMPOSE exec -T api python -m app.cli crear-usuario \
    '$ADMIN_MANTENIMIENTO' admin" <<< "$PASS_MANTENIMIENTO"$'\n'"$PASS_MANTENIMIENTO"

  CREDENCIALES="credenciales-$(date +%Y%m%d-%H%M%S).txt"
  {
    echo "DentalMaster — credenciales del primer arranque ($(date))"
    echo "Servidor: $SERVIDOR  ·  destino: ~/$DESTINO"
    echo
    echo "$ADMIN_CLINICA  (administración de la clínica)"
    echo "  contraseña: $PASS_CLINICA"
    echo
    echo "$ADMIN_MANTENIMIENTO  (mantenimiento técnico — usuario normal, con su propio rastro)"
    echo "  contraseña: $PASS_MANTENIMIENTO"
    echo
    echo "Cámbialas desde la aplicación o con:"
    echo "  ssh -t $SERVIDOR 'cd ~/$DESTINO && $COMPOSE exec api python -m app.cli cambiar-password <correo>'"
  } > "$CREDENCIALES"
  chmod 600 "$CREDENCIALES"

  echo
  echo "Guardadas en $(pwd)/$CREDENCIALES (no se sube al repo; bórralo tras guardarlas en un gestor de contraseñas)."
else
  echo
  echo "Listo: la API responde."
fi
