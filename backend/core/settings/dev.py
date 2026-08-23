"""Configuracoes de desenvolvimento."""

from core.settings.base import *  # noqa: F403
from core.settings.base import REST_FRAMEWORK

# Serve estaticos direto dos diretorios dos apps, sem exigir collectstatic. Fora do
# runserver o Django nao serve estaticos, e sem isto o admin fica sem CSS.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True

REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}
