from core.settings.base import *  # noqa: F403
from core.settings.base import REST_FRAMEWORK, env

WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True

API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=True)
LOG_CONVERSATION_CONTENT = env.bool("LOG_CONVERSATION_CONTENT", default=True)

REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}
