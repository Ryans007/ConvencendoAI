from decimal import Decimal

import pytest
from django.urls import reverse

from apps.llm.constants import ModelCategory
from apps.llm.models import LLMModel, LLMProvider

pytestmark = pytest.mark.django_db

_CHAT_FIELDS = ("input_price_per_million_tokens", "output_price_per_million_tokens")
_STT_FIELDS = ("price_per_audio_hour", "min_billed_audio_seconds")
_TTS_FIELDS = ("price_per_million_characters",)


@pytest.fixture
def admin_client(client, django_user_model):
    superuser = django_user_model.objects.create_superuser(
        username="chefe", email="chefe@empresa.com", password="Xk9#mQ2vLp8Z"
    )
    client.force_login(superuser)
    return client


def _model(category: str) -> LLMModel:
    provider = LLMProvider.objects.create(
        code="groq", name="Groq", base_url="https://api.groq.com/openai/v1", api_key="test-key"
    )
    return LLMModel.objects.create(
        provider=provider, category=category, model_id="m", display_name="m"
    )


def _fields_on_page(admin_client, model: LLMModel) -> set[str]:
    page = admin_client.get(reverse("admin:llm_llmmodel_change", args=[model.pk])).content.decode()
    every_field = _CHAT_FIELDS + _STT_FIELDS + _TTS_FIELDS
    return {field for field in every_field if f'name="{field}"' in page}


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        (ModelCategory.CHAT, _CHAT_FIELDS),
        (ModelCategory.STT, _STT_FIELDS),
        (ModelCategory.TTS, _TTS_FIELDS),
    ],
)
def test_the_change_page_shows_only_the_price_fields_of_the_models_category(
    admin_client, category, expected
):
    model = _model(category)

    assert _fields_on_page(admin_client, model) == set(expected)


def test_the_add_page_shows_every_price_field(admin_client):
    page = admin_client.get(reverse("admin:llm_llmmodel_add")).content.decode()

    for field in _CHAT_FIELDS + _STT_FIELDS + _TTS_FIELDS:
        assert f'name="{field}"' in page


def test_a_model_without_prices_is_valid_and_has_no_minimum(db):
    model = _model(ModelCategory.CHAT)

    assert model.input_price_per_million_tokens is None
    assert model.min_billed_audio_seconds == 0


def test_the_prices_are_stored_in_dollars_with_four_decimals():
    model = _model(ModelCategory.STT)
    model.price_per_audio_hour = Decimal("0.0400")
    model.min_billed_audio_seconds = 10
    model.save()

    model.refresh_from_db()

    assert model.price_per_audio_hour == Decimal("0.0400")
    assert model.min_billed_audio_seconds == 10
