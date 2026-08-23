"""Ponto de entrada WSGI, mantido para ferramentas que ainda o esperam."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.dev")

application = get_wsgi_application()
