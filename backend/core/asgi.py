"""Ponto de entrada ASGI, usado pelo worker do gunicorn e pelo uvicorn."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.dev")

application = get_asgi_application()
