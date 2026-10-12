import importlib
import os
import subprocess
import sys

import pytest
from django.test import Client, override_settings
from django.urls import clear_url_caches

import core.urls
from core.settings import prod


def _reload_urls() -> None:
    clear_url_caches()
    importlib.reload(core.urls)


@pytest.fixture
def reload_urls_after():
    """Restaura as rotas ao estado das configurações de teste depois do teste."""
    yield
    _reload_urls()


def test_api_docs_exist_when_enabled(reload_urls_after) -> None:
    """Com a variável ligada, a documentação da API responde."""
    with override_settings(API_DOCS_ENABLED=True):
        _reload_urls()
        response = Client().get("/api/schema/")

    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/api/schema/", "/api/docs/", "/api/redoc/"])
def test_api_docs_are_absent_when_disabled(reload_urls_after, path: str) -> None:
    """Desligada, a rota nem existe: nem a interface nem o esquema da API ficam públicos."""
    with override_settings(API_DOCS_ENABLED=False):
        _reload_urls()
        response = Client().get(path)

    assert response.status_code == 404


@pytest.mark.django_db
def test_health_answers_without_redirect_when_ssl_redirect_is_on() -> None:
    """A checagem interna do container chega por HTTP e não pode ser mandada para HTTPS."""
    with override_settings(
        SECURE_SSL_REDIRECT=True, SECURE_REDIRECT_EXEMPT=prod.SECURE_REDIRECT_EXEMPT
    ):
        response = Client().get("/api/health/")

    assert response.status_code == 200


def test_other_routes_are_redirected_when_ssl_redirect_is_on() -> None:
    """Só a saúde fica de fora: o resto continua sendo mandado para HTTPS."""
    with override_settings(
        SECURE_SSL_REDIRECT=True, SECURE_REDIRECT_EXEMPT=prod.SECURE_REDIRECT_EXEMPT
    ):
        response = Client().get("/api/auth/me/")

    assert response.status_code == 301
    assert response["Location"].startswith("https://")


def _settings_in_clean_process(*, drop: tuple[str, ...], extra: dict[str, str] | None = None):
    code = (
        "import core.wsgi\n"
        "from django.conf import settings\n"
        "print(settings.SETTINGS_MODULE, settings.DEBUG, settings.SECURE_SSL_REDIRECT, "
        "settings.API_DOCS_ENABLED, settings.LOG_CONVERSATION_CONTENT)\n"
    )
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(extra or {})
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
    )
    return result.stdout.split()


def test_missing_settings_module_falls_back_to_production() -> None:
    """Sem DJANGO_SETTINGS_MODULE, o servidor sobe sem depuração, com HTTPS e sem extras."""
    module, debug, ssl_redirect, api_docs, log_content = _settings_in_clean_process(
        drop=(
            "DJANGO_SETTINGS_MODULE",
            "DJANGO_DEBUG",
            "DJANGO_SECURE_SSL_REDIRECT",
            "API_DOCS_ENABLED",
            "LOG_CONVERSATION_CONTENT",
        )
    )

    assert module == "core.settings.prod"
    assert (debug, ssl_redirect, api_docs, log_content) == ("False", "True", "False", "False")


def test_ssl_redirect_can_only_be_disabled_explicitly() -> None:
    """O redirecionamento para HTTPS só desliga por variável explícita."""
    _, _, ssl_redirect, _, _ = _settings_in_clean_process(
        drop=("DJANGO_SETTINGS_MODULE",), extra={"DJANGO_SECURE_SSL_REDIRECT": "False"}
    )

    assert ssl_redirect == "False"


def test_development_turns_docs_and_conversation_log_on() -> None:
    """O desenvolvimento liga a documentação da API e o log de conversa, como sempre foi."""
    module, _, _, api_docs, log_content = _settings_in_clean_process(
        drop=("API_DOCS_ENABLED", "LOG_CONVERSATION_CONTENT"),
        extra={"DJANGO_SETTINGS_MODULE": "core.settings.dev"},
    )

    assert module == "core.settings.dev"
    assert (api_docs, log_content) == ("True", "True")
