# project/settings/flightplan.py

from .base import *

INSTALLED_APPS += [
    'flightplan',
]

ENV_PATH = os.getenv("ENV_FILE", ".env.flightplan")
environ.Env.read_env(ENV_PATH)
