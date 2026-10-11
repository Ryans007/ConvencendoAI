import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)

_BEFORE = [("llm", "0006_model_prices")]
_NAMED = [("llm", "0007_provider_api_key_env")]
_AFTER = [("llm", "0008_remove_provider_api_key")]
_SECRET = "SEGREDO-QUE-NUNCA-PODE-APARECER"


def _migrate(targets):
    """Leva o banco até as migrations pedidas e devolve os models daquele ponto da história."""
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return MigrationExecutor(connection).loader.project_state(targets).apps


def _provider_columns() -> set[str]:
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, "llm_llmprovider")
    return {column.name for column in description}


@pytest.fixture(autouse=True)
def back_to_the_latest_migration():
    """Devolve o banco à última migration, depois de apagar os provedores do teste.

    Um teste pode terminar com uma chave ainda no banco e a variável sem definir, e a guarda da
    migration seguinte, de propósito, não deixaria seguir; os provedores são só do teste.
    """
    yield
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM llm_llmprovider")
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())


def _provider(apps, code: str, key: str):
    return apps.get_model("llm", "LLMProvider").objects.create(
        code=code, name=code, base_url="https://x/v1", api_key=key
    )


def test_each_provider_gets_the_name_of_its_variable_and_keeps_the_key_for_now():
    apps = _migrate(_BEFORE)
    _provider(apps, "groq", "chave-groq")
    _provider(apps, "ollama-cloud", "chave-ollama")

    apps = _migrate(_NAMED)

    providers = {p.code: p for p in apps.get_model("llm", "LLMProvider").objects.all()}
    assert providers["groq"].api_key_env == "GROQ_API_KEY"
    assert providers["ollama-cloud"].api_key_env == "OLLAMA_CLOUD_API_KEY"
    assert providers["groq"].api_key == "chave-groq"


def test_removing_the_key_stops_and_lists_the_missing_variables_without_any_value(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_CLOUD_API_KEY", raising=False)
    apps = _migrate(_BEFORE)
    _provider(apps, "groq", _SECRET)
    _provider(apps, "ollama-cloud", "outra-chave")
    _migrate(_NAMED)

    with pytest.raises(RuntimeError) as failure:
        _migrate(_AFTER)

    message = str(failure.value)
    assert "GROQ_API_KEY" in message and "OLLAMA_CLOUD_API_KEY" in message
    assert _SECRET not in message and "outra-chave" not in message
    assert "api_key" in _provider_columns()
    apps = MigrationExecutor(connection).loader.project_state(_NAMED).apps
    assert apps.get_model("llm", "LLMProvider").objects.get(code="groq").api_key == _SECRET


def test_one_missing_variable_is_enough_to_stop_even_if_the_others_are_defined(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "definida")
    monkeypatch.delenv("OLLAMA_CLOUD_API_KEY", raising=False)
    apps = _migrate(_BEFORE)
    _provider(apps, "groq", "a")
    _provider(apps, "ollama-cloud", "b")
    _migrate(_NAMED)

    with pytest.raises(RuntimeError) as failure:
        _migrate(_AFTER)

    assert "OLLAMA_CLOUD_API_KEY" in str(failure.value)
    assert "GROQ_API_KEY" not in str(failure.value)


def test_a_blank_variable_counts_as_missing(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "   ")
    apps = _migrate(_BEFORE)
    _provider(apps, "groq", "a")
    _migrate(_NAMED)

    with pytest.raises(RuntimeError):
        _migrate(_AFTER)


def test_with_every_variable_defined_the_keys_leave_the_database(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "valor-do-ambiente")
    apps = _migrate(_BEFORE)
    _provider(apps, "groq", _SECRET)
    _migrate(_NAMED)

    apps = _migrate(_AFTER)

    assert "api_key" not in _provider_columns()
    assert "api_key_env" in _provider_columns()
    provider = apps.get_model("llm", "LLMProvider").objects.get(code="groq")
    assert provider.api_key_env == "GROQ_API_KEY"


def test_a_provider_without_a_stored_key_does_not_need_the_variable(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    apps = _migrate(_BEFORE)
    _provider(apps, "groq", "")
    _migrate(_NAMED)

    _migrate(_AFTER)

    assert "api_key" not in _provider_columns()


def test_undoing_the_migration_gives_the_key_back_from_the_environment(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "valor-do-ambiente")
    apps = _migrate(_BEFORE)
    _provider(apps, "groq", "valor-antigo")
    _migrate(_NAMED)
    _migrate(_AFTER)

    apps = _migrate(_NAMED)

    assert apps.get_model("llm", "LLMProvider").objects.get(code="groq").api_key == (
        "valor-do-ambiente"
    )
