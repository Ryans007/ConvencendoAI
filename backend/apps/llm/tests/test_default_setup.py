import pytest

from apps.llm.constants import ModelCategory, StructuredOutputMethod
from apps.llm.models import AgentModelConfig, LLMModel, LLMProvider
from apps.llm.services.default_setup import apply_default_setup

pytestmark = pytest.mark.django_db


def _roles() -> dict[str, str | None]:
    config = AgentModelConfig.get_solo()
    return {
        role: getattr(config, role).model_id if getattr(config, role) else None
        for role in ("persona_model", "judge_model", "router_model", "stt_model", "tts_model")
    }


def test_an_empty_database_ends_up_fully_configured():
    report = apply_default_setup("gsk_ambiente")

    provider = LLMProvider.objects.get(code="groq")
    assert provider.base_url == "https://api.groq.com/openai/v1"
    assert provider.api_key == "gsk_ambiente"
    assert set(provider.models.values_list("model_id", "category")) == {
        ("openai/gpt-oss-20b", ModelCategory.CHAT),
        ("openai/gpt-oss-120b", ModelCategory.CHAT),
        ("whisper-large-v3-turbo", ModelCategory.STT),
        ("canopylabs/orpheus-v1-english", ModelCategory.TTS),
    }
    assert all(provider.models.values_list("is_active", flat=True))
    assert _roles() == {
        "persona_model": "openai/gpt-oss-20b",
        "judge_model": "openai/gpt-oss-120b",
        "router_model": "openai/gpt-oss-120b",
        "stt_model": "whisper-large-v3-turbo",
        "tts_model": "canopylabs/orpheus-v1-english",
    }
    assert report.provider_created and report.key_stored and report.has_key
    assert len(report.models_created) == 4 and len(report.roles_filled) == 5


def test_the_gpt_oss_models_use_strict_json_schema():
    apply_default_setup("gsk_ambiente")

    methods = LLMModel.objects.filter(model_id__startswith="openai/gpt-oss").values_list(
        "structured_output_method", flat=True
    )
    assert list(methods) == [StructuredOutputMethod.JSON_SCHEMA_STRICT] * 2


def test_running_twice_creates_nothing_the_second_time():
    apply_default_setup("gsk_ambiente")

    report = apply_default_setup("gsk_ambiente")

    assert not report.changed_anything
    assert LLMProvider.objects.count() == 1
    assert LLMModel.objects.count() == 4
    assert len(report.models_existing) == 4 and len(report.roles_kept) == 5


def test_a_key_registered_in_the_admin_is_not_overwritten():
    LLMProvider.objects.create(
        code="groq", name="Groq", base_url="https://api.groq.com/openai/v1", api_key="gsk_admin"
    )

    report = apply_default_setup("gsk_ambiente")

    assert LLMProvider.objects.get(code="groq").api_key == "gsk_admin"
    assert not report.key_stored and report.has_key


def test_a_role_already_filled_is_kept():
    other = LLMProvider.objects.create(code="outro", name="Outro", base_url="https://x/v1")
    chosen = LLMModel.objects.create(provider=other, model_id="meu-modelo", display_name="Meu")
    config = AgentModelConfig.get_solo()
    config.persona_model = chosen
    config.save()

    report = apply_default_setup("gsk_ambiente")

    assert _roles()["persona_model"] == "meu-modelo"
    assert _roles()["judge_model"] == "openai/gpt-oss-120b"
    assert report.roles_kept == ["persona_model"]


def test_an_existing_inactive_model_is_left_alone():
    provider = LLMProvider.objects.create(
        code="groq", name="Groq", base_url="https://api.groq.com/openai/v1"
    )
    LLMModel.objects.create(
        provider=provider,
        model_id="openai/gpt-oss-20b",
        display_name="Desligado",
        is_active=False,
    )

    apply_default_setup("gsk_ambiente")

    model = LLMModel.objects.get(model_id="openai/gpt-oss-20b")
    assert not model.is_active
    assert model.display_name == "Desligado"
    assert model.structured_output_method == StructuredOutputMethod.TOOL_CALLING
    assert LLMModel.objects.filter(model_id="openai/gpt-oss-20b").count() == 1


@pytest.mark.parametrize("missing", ["", "   ", None])
def test_without_a_key_the_rest_is_created_and_the_provider_has_no_key(missing):
    report = apply_default_setup(missing)

    provider = LLMProvider.objects.get(code="groq")
    assert not provider.has_api_key
    assert LLMModel.objects.count() == 4
    assert None not in _roles().values()
    assert not report.has_key and not report.key_stored


def test_a_key_that_arrives_later_is_stored():
    apply_default_setup("")

    report = apply_default_setup("gsk_chegou")

    assert LLMProvider.objects.get(code="groq").api_key == "gsk_chegou"
    assert report.key_stored
