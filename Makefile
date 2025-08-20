# =========[ Config ]=========
PY        ?= python
DJ        ?= $(PY) manage.py
SETTINGS  ?= project.settings.suite
PROD_APP  ?= heroku-12bytes

# Local env file for your “staging” (local) profile
ENV_AIRBORNE_LOCAL ?= .env.airborne_local

# Defaults for seeding a local superuser
SU_USERNAME ?= admin
SU_EMAIL    ?= admin@example.com
SU_PASSWORD ?= admin123

# =========[ Help ]=========
.PHONY: help
help:
	@echo "Targets:"
	@echo "  run-airborne-local           - Run local server (.env.airborne_local)"
	@echo "  migrate-airborne-local       - Apply migrations locally"
	@echo "  seed-local-superuser         - Create/refresh a local superuser"
	@echo "  pull-prod-to-local           - Pull Heroku PROD DB -> local"
	@echo "  reset-and-pull-prod-to-local - Drop/recreate local DB, then pull"
	@echo "  dbinfo-airborne-local        - Print local DB settings seen by Django"
	@echo "  logs-prod / open-prod        - Tail logs / open Heroku PROD"
	@echo "  migrate-prod                 - Run migrations on Heroku PROD"

# =========[ Local: Airborne profile ]=========
.PHONY: run-airborne-local migrate-airborne-local dbinfo-airborne-local
run-airborne-local:
	ENV_FILE=$(ENV_AIRBORNE_LOCAL) DJANGO_SETTINGS_MODULE=$(SETTINGS) $(DJ) runserver

migrate-airborne-local:
	ENV_FILE=$(ENV_AIRBORNE_LOCAL) DJANGO_SETTINGS_MODULE=$(SETTINGS) $(DJ) migrate

makemigrations-airborne-local:
	ENV_FILE=$(ENV_AIRBORNE_LOCAL) DJANGO_SETTINGS_MODULE=$(SETTINGS) $(DJ) makemigrations

dbinfo-airborne-local:
	ENV_FILE=$(ENV_AIRBORNE_LOCAL) DJANGO_SETTINGS_MODULE=$(SETTINGS) \
	$(PY) -c 'from django.conf import settings; db=settings.DATABASES["default"]; print("ENGINE:",db.get("ENGINE")); print("NAME  :",db.get("NAME")); print("HOST  :",db.get("HOST")); print("USER  :",db.get("USER"))'

# =========[ Seed a local superuser ]=========
.PHONY: seed-local-superuser
seed-local-superuser:
	@echo "Seeding local superuser '$(SU_USERNAME)'..."
	ENV_FILE=$(ENV_AIRBORNE_LOCAL) DJANGO_SETTINGS_MODULE=$(SETTINGS) \
	SU_USERNAME="$(SU_USERNAME)" SU_EMAIL="$(SU_EMAIL)" SU_PASSWORD="$(SU_PASSWORD)" \
	$(PY) -c 'from django.contrib.auth import get_user_model; import os; U=get_user_model(); un=os.environ.get("SU_USERNAME","admin"); em=os.environ.get("SU_EMAIL","admin@example.com"); pw=os.environ.get("SU_PASSWORD","admin123"); u,created=U.objects.get_or_create(username=un, defaults={"email": em}); u.email=em or u.email; u.is_staff=True; u.is_superuser=True; u.set_password(pw); u.save(); print(("Created" if created else "Updated"), "superuser:", u.username)'

# =========[ Pull PROD DB -> local ]=========
.PHONY: pull-prod-to-local reset-and-pull-prod-to-local
pull-prod-to-local:
	@echo "Pulling Heroku PROD DB into local (airborne)…"
	@SOURCE_URL=$$(heroku config:get DATABASE_URL -a $(PROD_APP)); \
	pg_dump "$$SOURCE_URL?sslmode=require" --no-owner --no-acl --no-event-triggers | \
	psql "postgres://tomstout:Cassie2001@127.0.0.1:5432/12bytes_airborne_local?sslmode=disable"

reset-and-pull-prod-to-local:
	psql -h 127.0.0.1 -p 5432 -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='12bytes_airborne_local';" || true
	dropdb  -h 127.0.0.1 -p 5432 -U postgres 12bytes_airborne_local || true
	createdb -h 127.0.0.1 -p 5432 -U postgres -O tomstout 12bytes_airborne_local
	$(MAKE) pull-prod-to-local

# =========[ Heroku: PROD helpers ]=========
.PHONY: logs-prod open-prod migrate-prod
logs-prod:
	heroku logs -t -a $(PROD_APP)

open-prod:
	heroku open -a $(PROD_APP)


migrate-prod:
	heroku run -a $(PROD_APP) -- python manage.py migrate --noinpu