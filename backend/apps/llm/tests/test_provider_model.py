import pytest
from django.db import connection

from apps.llm.models import LLMProvider

pytestmark = pytest.mark.django_db

_LONG = "gsk_abcdefghijklmnopqrstuvwxyz123456"


def _provider(**kwargs) -> LLMProvider:
    return LLMProvider.objects.create(
        code="groq", name="Groq", base_url="https://api.groq.com/openai/v1", **kwargs
    )


def test_the_key_given_on_create_is_the_key_of_the_provider():
    provider = _provider(api_key="gsk_abc123XYZ")

    provider.refresh_from_db()

    assert provider.api_key == "gsk_abc123XYZ"
    assert provider.has_api_key


def test_spaces_around_the_key_are_dropped():
    provider = _provider(api_key="  gsk_abc123XYZ  ")

    provider.refresh_from_db()

    assert provider.api_key == "gsk_abc123XYZ"


def test_assigning_a_new_key_replaces_the_old_one():
    provider = _provider(api_key="primeira")

    provider.api_key = "segunda"
    provider.save()
    provider.refresh_from_db()

    assert provider.api_key == "segunda"


def test_a_provider_without_a_key_has_no_key():
    provider = _provider()

    assert provider.api_key == ""
    assert not provider.has_api_key
    assert provider.api_key_hint == ""


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_a_blank_key_counts_as_no_key(blank):
    provider = _provider(api_key=blank)

    assert not provider.has_api_key
    assert provider.api_key_encrypted == ""


def test_no_column_of_the_provider_holds_the_plain_key():
    provider = _provider(api_key="gsk_SEGREDO123")

    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM llm_llmprovider WHERE id = %s", [provider.pk])
        row = cursor.fetchone()

    assert all("gsk_SEGREDO123" not in str(value) for value in row)
    assert all("SEGREDO" not in str(value) for value in row)


def test_a_long_key_shows_only_its_first_six_characters():
    hint = _provider(api_key=_LONG).api_key_hint

    assert hint.startswith("gsk_ab")
    assert "gsk_abc" not in hint
    assert "ghijklmnopqrstuvwxyz123456" not in hint


def test_a_short_key_shows_at_most_a_quarter_of_it():
    hint = _provider(api_key="abcdefgh").api_key_hint

    assert hint.startswith("ab")
    assert "abc" not in hint


def test_the_mask_does_not_reveal_the_length_of_the_key():
    short = _provider(api_key="abcdefgh").api_key_hint
    long = LLMProvider.objects.create(
        code="outro", name="Outro", base_url="https://x/v1", api_key=_LONG
    ).api_key_hint

    assert short[2:] == long[6:]


def test_a_key_that_no_longer_opens_counts_as_no_key(settings):
    settings.SECRET_KEY = "uma-chave-secreta"
    provider = _provider(api_key=_LONG)

    settings.SECRET_KEY = "outra-chave-secreta"
    provider.refresh_from_db()

    assert not provider.has_api_key
    assert provider.api_key_hint == ""
