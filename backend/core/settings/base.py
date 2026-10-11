from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",
    "channels",
]

LOCAL_APPS = [
    "apps.users",
    "apps.catalog",
    "apps.progress",
    "apps.llm",
    "apps.agents",
    "apps.voice",
    "apps.review",
    "apps.usage",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"
ASGI_APPLICATION = "core.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", default="db"),
        "PORT": env.int("POSTGRES_PORT", default=5432),
    }
}

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        "apps.users.permissions.PasswordChangeNotRequired",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "CHECK_REVOKE_TOKEN": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "ConvencendoAI",
    "DESCRIPTION": (
        "ConvencendoAI é um sistema multiagente de conversação por voz para prática de "
        "inglês falado. O aluno pratica cenários realistas de conversação com duas "
        "personas simultâneas, organizados em trilhas com arco narrativo — cada cenário "
        "é uma tarefa com objetivo verificável e critérios de aceite ocultos até o "
        "relatório final. Ao fim de cada execução, um agente avaliador atribui uma nota "
        "de 0 a 100 por rubrica ponderada.\n\n"
        "Esta API expõe o que uma interface precisa para acompanhar essa jornada: "
        "**autenticação** (registro, login, renovação e logout, por token JWT), a "
        "**jornada** do aluno (trilhas, cenários e níveis, com o progresso já calculado "
        "a partir das tentativas reais dele), o **briefing** de um cenário antes de "
        "começar (objetivo, contexto e elenco — nunca os critérios de aceite nem os "
        "pesos da rubrica, que só aparecem depois), e o **relatório** de uma tentativa já "
        "concluída (nota final, sub-nota por dimensão, e o resultado de cada critério).\n\n"
        "A execução do cenário em si não passa por esta API: por texto, é um management "
        "command interno; por voz, é uma conexão WebSocket em "
        "`/ws/voice/<cenario>/<nivel>/?token=...`, autenticada com o mesmo token de "
        "acesso emitido aqui."
    ),
    "VERSION": "1.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "TAGS": [
        {
            "name": "auth",
            "description": "Registro de conta, login, renovação e logout — por token JWT.",
        },
        {
            "name": "journey",
            "description": "A jornada do aluno: trilhas, cenários e níveis, com o progresso calculado.",
        },
        {
            "name": "scenarios",
            "description": "Briefing pré-sessão de um cenário e nível, sem revelar os critérios de aceite.",
        },
        {
            "name": "attempts",
            "description": "Relatório de uma tentativa já concluída — nota, sub-notas e critérios.",
        },
    ],
}

CORS_ALLOWED_ORIGINS = env.list("DJANGO_CORS_ALLOWED_ORIGINS", default=[])
