import pytest
from django.urls import reverse

from apps.llm.models import LLMProvider

pytestmark = pytest.mark.django_db

_SECRET = "gsk_VALOR-SECRETO-DA-CHAVE-123456"
_VARIABLE = "LLM_TEST_API_KEY"


@pytest.fixture
def admin_client(client, django_user_model):
    superuser = django_user_model.objects.create_superuser(
        username="chefe", email="chefe@empresa.com", password="Xk9#mQ2vLp8Z"
    )
    client.force_login(superuser)
    return client


@pytest.fixture
def provider() -> LLMProvider:
    return LLMProvider.objects.create(
        code="groq", name="Groq", base_url="https://api.groq.com/openai/v1", api_key_env=_VARIABLE
    )


def _pages(admin_client, provider) -> list[str]:
    urls = [
        reverse("admin:llm_llmprovider_changelist"),
        reverse("admin:llm_llmprovider_change", args=[provider.pk]),
        reverse("admin:llm_llmprovider_add"),
    ]
    return [admin_client.get(url).content.decode() for url in urls]


def test_no_admin_page_shows_any_part_of_the_key(admin_client, provider, monkeypatch):
    monkeypatch.setenv(_VARIABLE, _SECRET)

    for page in _pages(admin_client, provider):
        assert _SECRET not in page
        assert "VALOR-SECRETO" not in page
        assert "gsk_" not in page
        assert "123456" not in page


def test_the_admin_says_the_variable_is_defined_when_it_is(admin_client, provider, monkeypatch):
    monkeypatch.setenv(_VARIABLE, _SECRET)

    changelist, change, _ = _pages(admin_client, provider)

    assert _VARIABLE in changelist and "definida" in changelist
    assert "não definida" not in changelist
    assert _VARIABLE in change and "definida" in change


def test_the_admin_says_the_variable_is_not_defined_when_it_is_missing(
    admin_client, provider, monkeypatch
):
    monkeypatch.delenv(_VARIABLE, raising=False)

    changelist, change, _ = _pages(admin_client, provider)

    assert "não definida" in changelist
    assert "não definida" in change


def test_a_blank_variable_is_shown_as_not_defined(admin_client, provider, monkeypatch):
    monkeypatch.setenv(_VARIABLE, "   ")

    changelist, _, _ = _pages(admin_client, provider)

    assert "não definida" in changelist


def test_only_the_name_of_the_variable_is_stored(admin_client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", _SECRET)

    response = admin_client.post(
        reverse("admin:llm_llmprovider_add"),
        {
            "name": "Groq",
            "code": "groq",
            "base_url": "https://api.groq.com/openai/v1",
            "api_key_env": "GROQ_API_KEY",
            "is_active": "on",
        },
    )

    assert response.status_code == 302
    provider = LLMProvider.objects.get(code="groq")
    assert provider.api_key_env == "GROQ_API_KEY"
    stored = " ".join(str(getattr(provider, f.name)) for f in LLMProvider._meta.fields)
    assert _SECRET not in stored


@pytest.mark.parametrize("name", ["groq_api_key", "1GROQ", "GROQ-KEY", "GROQ KEY", "gsk_abc123"])
def test_a_name_that_is_not_an_environment_variable_is_refused_with_the_expected_format(
    admin_client, name
):
    response = admin_client.post(
        reverse("admin:llm_llmprovider_add"),
        {
            "name": "Groq",
            "code": "groq",
            "base_url": "https://api.groq.com/openai/v1",
            "api_key_env": name,
            "is_active": "on",
        },
    )

    assert response.status_code == 200
    assert "maiúsculas" in response.content.decode()
    assert not LLMProvider.objects.exists()


def test_pasting_a_real_key_in_the_name_field_is_refused_and_not_saved(admin_client):
    response = admin_client.post(
        reverse("admin:llm_llmprovider_add"),
        {
            "name": "Groq",
            "code": "groq",
            "base_url": "https://api.groq.com/openai/v1",
            "api_key_env": _SECRET,
            "is_active": "on",
        },
    )

    assert not LLMProvider.objects.exists()
    assert response.status_code == 200
