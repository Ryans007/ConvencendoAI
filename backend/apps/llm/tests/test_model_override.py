import contextvars

import pytest

from apps.llm.constants import ModelCategory, ModelPurpose
from apps.llm.models import AgentModelConfig, LLMModel, LLMProvider
from apps.llm.services.factory import ModelNotConfigured, get_llm
from apps.llm.services.model_override import current_override, override_models

pytestmark = pytest.mark.django_db


@pytest.fixture
def provider() -> LLMProvider:
    return LLMProvider.objects.create(
        code="groq",
        name="Groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="LLM_TEST_API_KEY",
    )


def _chat(provider: LLMProvider, model_id: str, **extra) -> LLMModel:
    return LLMModel.objects.create(
        provider=provider, model_id=model_id, display_name=model_id, **extra
    )


@pytest.fixture
def configured(provider) -> LLMModel:
    small = _chat(provider, "small-model")
    config = AgentModelConfig.get_solo()
    config.persona_model = small
    config.save()
    return small


def test_without_an_override_the_configured_model_is_used(configured):
    assert get_llm(ModelPurpose.PERSONA).model_name == "small-model"
    assert current_override(ModelPurpose.PERSONA) is None


def test_inside_the_block_the_chosen_model_is_used(configured, provider):
    large = _chat(provider, "large-model")

    with override_models({ModelPurpose.PERSONA: large}):
        assert get_llm(ModelPurpose.PERSONA).model_name == "large-model"

    assert get_llm(ModelPurpose.PERSONA).model_name == "small-model"


def test_the_saved_configuration_never_changes(configured, provider):
    large = _chat(provider, "large-model")

    with override_models({ModelPurpose.PERSONA: large}):
        get_llm(ModelPurpose.PERSONA)

    assert AgentModelConfig.get_solo().persona_model_id == configured.pk


def test_another_context_running_at_the_same_time_keeps_the_configured_model(configured, provider):
    large = _chat(provider, "large-model")
    elsewhere = contextvars.Context()

    with override_models({ModelPurpose.PERSONA: large}):
        used_elsewhere = elsewhere.run(lambda: get_llm(ModelPurpose.PERSONA).model_name)

    assert used_elsewhere == "small-model"


def test_a_role_without_a_choice_keeps_using_the_configuration(configured, provider):
    large = _chat(provider, "large-model")
    config = AgentModelConfig.get_solo()
    config.router_model = configured
    config.save()

    with override_models({ModelPurpose.PERSONA: large}):
        assert get_llm(ModelPurpose.ROUTER).model_name == "small-model"


def test_a_model_of_another_category_is_refused_before_any_call(configured, provider):
    speech = _chat(provider, "voice-model", category=ModelCategory.TTS)

    with pytest.raises(ValueError, match="voice-model"):
        with override_models({ModelPurpose.PERSONA: speech}):
            pass


def test_an_unknown_role_is_refused(configured, provider):
    with pytest.raises(ValueError, match="Papel desconhecido"):
        with override_models({"narrator": configured}):
            pass


def test_an_inactive_model_is_refused_like_in_the_normal_path(configured, provider):
    inactive = _chat(provider, "inactive-model", is_active=False)

    with override_models({ModelPurpose.PERSONA: inactive}):
        with pytest.raises(ModelNotConfigured):
            get_llm(ModelPurpose.PERSONA)


def test_a_provider_without_the_key_is_refused_like_in_the_normal_path(configured):
    keyless = LLMProvider.objects.create(
        code="no-key",
        name="Sem chave",
        base_url="https://example.com/v1",
        api_key_env="KEY_THAT_IS_NOT_SET",
    )
    model = _chat(keyless, "keyless-model")

    with override_models({ModelPurpose.PERSONA: model}):
        with pytest.raises(ModelNotConfigured, match="KEY_THAT_IS_NOT_SET"):
            get_llm(ModelPurpose.PERSONA)
