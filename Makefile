# Atajos de desarrollo. Todo corre en Docker: no hace falta Python local.
.DEFAULT_GOAL := help
COMPOSE := docker compose
RUFF := docker run --rm -v "$(PWD):/src" -w /src --entrypoint ruff dentalmasterapi-api

help:  ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up:  ## Levanta el stack con datos demo
	$(COMPOSE) up -d --build

desplegar:  ## Sube la API al VPS y la levanta con Docker (ver scripts/desplegar.sh)
	scripts/desplegar.sh

down:  ## Detiene el stack (conserva los datos)
	$(COMPOSE) down

reset:  ## Recrea la base desde cero: vuelve a correr 01/02/03
	$(COMPOSE) down -v && $(COMPOSE) up -d --build

vacio:  ## Base SIN datos demo: catálogos, la clínica y un administrador (para probar creándolo todo)
	$(COMPOSE) -f docker-compose.yml down -v
	$(COMPOSE) -f docker-compose.yml up -d --build
	@until curl -sf localhost:8000/health >/dev/null; do sleep 2; done
	@$(COMPOSE) -f docker-compose.yml exec -T -e PASSWORD_INICIAL="$(or $(PASSWORD_INICIAL),Sonrisa-Prueba-7392)" api \
	  python -m app.cli iniciar-clinica "$(or $(ADMIN),admin@dentalsonrisa.do)" "$(or $(CLINICA),Mi clínica)"

logs:  ## Sigue los logs de la API
	$(COMPOSE) logs -f api

verify:  ## Ejecuta las 101 aserciones de db/99_verify.sql; falla si alguna no pasa
	@$(COMPOSE) exec -T db psql -U dental -d odonto -f /db/99_verify.sql > verificacion.txt 2>&1; estado=$$?; \
	sed -n '/RESUMEN/,$$p' verificacion.txt; \
	[ $$estado -eq 0 ] || { tail -n 5 verificacion.txt; exit $$estado; }

test:  ## Corre la suite de pytest
	$(COMPOSE) exec -T api pytest

lint:  ## ruff check + format --check
	$(RUFF) check app tests migrations && $(RUFF) format --check app tests migrations

fmt:  ## Aplica el formateo de ruff
	$(RUFF) format app tests migrations && $(RUFF) check --fix app tests migrations

psql:  ## Abre una sesión psql contra la base
	$(COMPOSE) exec db psql -U dental -d odonto

.PHONY: help up down reset logs verify test lint fmt psql
