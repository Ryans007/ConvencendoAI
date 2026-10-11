import pytest


@pytest.fixture(autouse=True)
def provider_api_key(monkeypatch):
    """Define a chave de teste dos provedores, que na aplicação vem do ambiente do servidor.

    Os testes cadastram o provedor com `api_key_env="LLM_TEST_API_KEY"`; sem a variável o
    provedor seria tratado como sem chave. Quem testa a ausência da chave a remove.
    """
    monkeypatch.setenv("LLM_TEST_API_KEY", "test-key")
