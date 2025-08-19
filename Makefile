# make run-skyguy
# make migrate-skyguy

# make run-airborne
# make migrate-airborne_images

# ENV VARS
ENV_SKYGUY=.env.skyguy
ENV_AIRBORNE=.env.airborne_images


# ─── RUNSERVER ──────────────────────────────────────────────
run-skyguy:
	ENV_FILE=.env.skyguy DJANGO_SETTINGS_MODULE=project.settings.suite python manage.py runserver

run-airborne:
	ENV_FILE=.env.airborne_images DJANGO_SETTINGS_MODULE=project.settings.suite python manage.py runserver

run-dev:
	ENV_FILE=.env.local DJANGO_SETTINGS_MODULE=project.settings.suite python manage.py runserver

# ─── MIGRATIONS ─────────────────────────────────────────────
migrate-skyguy:
	ENV_FILE=$(ENV_SKYGUY) DJANGO_SETTINGS_MODULE=project.settings.suite python manage.py migrate

migrate-airborne:
	ENV_FILE=$(ENV_AIRBORNE) DJANGO_SETTINGS_MODULE=project.settings.suite python manage.py migrate

migrate-local:
	ENV_FILE=.env.local DJANGO_SETTINGS_MODULE=project.settings.suite python manage.py migrate

	
makemigrations:
	ENV_FILE=$(ENV_AIRBORNE) DJANGO_SETTINGS_MODULE=project.settings.suite python3 manage.py makemigrations

makemigrations-airborne:
	ENV_FILE=$(ENV_AIRBORNE) DJANGO_SETTINGS_MODULE=project.settings.suite python3 manage.py makemigrations

makemigrations-skyguy:
	ENV_FILE=$(ENV_SKYGUY) DJANGO_SETTINGS_MODULE=project.settings.suite python3 manage.py makemigrations

makemigrations-local:
	ENV_FILE=.env.local DJANGO_SETTINGS_MODULE=project.settings.suite python manage.py makemigrations


# ─── SHELL ──────────────────────────────────────────────────
shell-skyguy:
	ENV_FILE=$(ENV_SKYGUY) DJANGO_SETTINGS_MODULE=project.settings.suite python manage.py shell

shell-airborne:
	ENV_FILE=$(ENV_AIRBORNE) DJANGO_SETTINGS_MODULE=project.settings.suite python manage.py shell

# ─── COLLECTSTATIC ──────────────────────────────────────────
collectstatic-skyguy:
	ENV_FILE=$(ENV_SKYGUY) DJANGO_SETTINGS_MODULE=project.settings.suite python manage.py collectstatic --noinput

collectstatic-airborne:
	ENV_FILE=$(ENV_AIRBORNE) DJANGO_SETTINGS_MODULE=project.settings.suite python manage.py collectstatic --noinput

# ─── BACKUP ─────────────────────────────────────────────────
backup-skyguy:
	ENV_FILE=$(ENV_SKYGUY) DJANGO_SETTINGS_MODULE=project.settings.suite python manage.py dbbackup

backup-airborne:
	ENV_FILE=$(ENV_AIRBORNE) DJANGO_SETTINGS_MODULE=project.settings.suite python manage.py dbbackup

# ─── TESTING ────────────────────────────────────────────────
test-skyguy:
	ENV_FILE=$(ENV_SKYGUY) DJANGO_SETTINGS_MODULE=project.settings.suite python manage.py test

test-airborne:
	ENV_FILE=$(ENV_AIRBORNE) DJANGO_SETTINGS_MODULE=project.settings.suite python manage.py test


.PHONY: run-skyguy run-airborne migrate-skyguy migrate-airborne shell-skyguy shell-airborne collectstatic-skyguy collectstatic-airborne backup-skyguy backup-airborne test-skyguy test-airborne


# ─── FULL DEPLOY ─────────────────────────────────────────────
full-deploy-airborne:
	git checkout client-airborne
	git pull origin main
	git push origin client-airborne
	heroku run python manage.py migrate -a airborne-images-12bytes
	heroku run python manage.py collectstatic --noinput -a airborne-images-12bytes
	heroku restart -a airborne-images-12bytes

full-deploy-skyguy:
	git checkout client-skyguy
	git pull origin main
	git push origin client-skyguy
	heroku run python manage.py migrate -a skyguy-12bytes
	heroku run python manage.py collectstatic --noinput -a skyguy-12bytes
	heroku restart -a skyguy-12bytes
