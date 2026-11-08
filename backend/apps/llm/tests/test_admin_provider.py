import pytest
from django.urls import reverse

from apps.llm.models import LLMProvider

pytestmark = pytest.mark.django_db

_SECRET = "gsk_abcdefVALOR-SECRETO-DA-CHAVE-123456"
_HIDDEN_PIECES = [_SECRET, "abcdefV", "VALOR-SECRETO", "123456"]


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
        code="groq", name="Groq", base_url="https://api.groq.com/openai/v1", api_key=_SECRET
    )


def _change_url(provider: LLMProvider) -> str:
    return reverse("admin:llm_llmprovider_change", args=[provider.pk])


def _pages(admin_client, provider) -> list[str]:
    urls = [
        reverse("admin:llm_llmprovider_changelist"),
        _change_url(provider),
        reverse("admin:llm_llmprovider_add"),
    ]
    return [admin_client.get(url).content.decode() for url in urls]


def _form(**overrides) -> dict:
    data = {
        "name": "Groq",
        "code": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "new_api_key": "",
        "is_active": "on",
    }
    data.update(overrides)
    return data


def test_creating_a_provider_with_a_key_stores_that_key(admin_client):
    response = admin_client.post(
        reverse("admin:llm_llmprovider_add"), _form(new_api_key="  gsk_abc123XYZ  ")
    )

    assert response.status_code == 302
    assert LLMProvider.objects.get(code="groq").api_key == "gsk_abc123XYZ"


def test_creating_a_provider_without_a_key_shows_it_as_not_defined(admin_client):
    response = admin_client.post(reverse("admin:llm_llmprovider_add"), _form())

    assert response.status_code == 302
    provider = LLMProvider.objects.get(code="groq")
    assert not provider.has_api_key
    assert "não definida" in admin_client.get(_change_url(provider)).content.decode()


def test_the_form_does_not_ask_for_an_environment_variable(admin_client):
    page = admin_client.get(reverse("admin:llm_llmprovider_add")).content.decode()

    assert "api_key_env" not in page
    assert "variável de ambiente" not in page
    assert 'name="new_api_key"' in page


def test_saving_with_an_empty_new_key_keeps_the_current_key(admin_client, provider):
    response = admin_client.post(_change_url(provider), _form(name="Groq Cloud"))

    assert response.status_code == 302
    provider.refresh_from_db()
    assert provider.name == "Groq Cloud"
    assert provider.api_key == _SECRET


def test_saving_with_a_new_key_replaces_the_current_key(admin_client, provider):
    response = admin_client.post(_change_url(provider), _form(new_api_key="gsk_nova999"))

    assert response.status_code == 302
    provider.refresh_from_db()
    assert provider.api_key == "gsk_nova999"


def test_the_new_key_box_opens_empty(admin_client, provider):
    page = admin_client.get(_change_url(provider)).content.decode()

    box = page[page.index('name="new_api_key"') :]
    box = box[: box.index(">")]
    assert 'type="password"' in page
    assert "value=" not in box


def test_the_changelist_and_the_change_page_show_only_the_start_of_the_key(admin_client, provider):
    changelist, change, _ = _pages(admin_client, provider)

    for page in (changelist, change):
        assert "gsk_ab••••••••" in page
        assert "não definida" not in page


def test_no_admin_page_contains_the_full_key(admin_client, provider):
    for page in _pages(admin_client, provider):
        for piece in _HIDDEN_PIECES:
            assert piece not in page


def test_a_form_sent_back_with_an_error_does_not_echo_the_typed_key(admin_client):
    response = admin_client.post(
        reverse("admin:llm_llmprovider_add"), _form(base_url="nao-e-url", new_api_key=_SECRET)
    )

    assert response.status_code == 200
    page = response.content.decode()
    for piece in _HIDDEN_PIECES:
        assert piece not in page
    assert not LLMProvider.objects.exists()


def test_a_provider_without_a_key_is_shown_as_not_defined(admin_client):
    keyless = LLMProvider.objects.create(code="sem", name="Sem chave", base_url="https://x/v1")

    changelist, change, _ = _pages(admin_client, keyless)

    assert "não definida" in changelist
    assert "não definida" in change
