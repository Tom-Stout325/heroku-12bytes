# Makefile for SkyGuy local environment

ENV_FILE=.env.skyguy_local
DJANGO_SETTINGS=project.settings.suite
PYTHON=python

# Run Django commands with SkyGuy env
manage:
	ENV_FILE=$(ENV_FILE) DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) $(PYTHON) manage.py $(CMD)

makemigrations:
	ENV_FILE=$(ENV_FILE) DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) $(PYTHON) manage.py makemigrations

migrate:
	ENV_FILE=$(ENV_FILE) DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) $(PYTHON) manage.py migrate

runserver:
	ENV_FILE=$(ENV_FILE) DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) $(PYTHON) manage.py runserver

shell:
	ENV_FILE=$(ENV_FILE) DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) $(PYTHON) manage.py shell

createsuperuser:
	ENV_FILE=$(ENV_FILE) DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) $(PYTHON) manage.py createsuperuser

# View Heroku logs for the SkyGuy app
heroku-logs:
	heroku logs --tail --app skyguy-12bytes
