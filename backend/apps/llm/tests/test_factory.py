from dataclasses import dataclass

import pytest

from apps.llm.constants import ModelPurpose
from apps.llm.models import AgentModelConfig, LLMModel, LLMProvider
from apps.llm.services import factory
from apps.llm.services.factory import ModelNotConfigured, get_llm

pytestmark = pytest.mark.django_db


def _make_model(*, provider_active: bool = True, model_active: bool = True) -> LLMModel:
    provider = LLMProvider.objects.create(
        code="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        is_active=provider_active,
    )
    return LLMModel.objects.create(
        provider=provider,
        model_id="gpt-4o-mini",
        display_name="GPT-4o mini",
        is_active=model_active,
    )


def test_get_llm_builds_client_with_configured_parameters():
    model = _make_model()
    config = AgentModelConfig.get_solo()
    config.persona_model = model
    config.judge_model = model
    config.save()

    persona_llm = get_llm(ModelPurpose.PERSONA)
    judge_llm = get_llm(ModelPurpose.JUDGE)

    assert persona_llm.model_name == "gpt-4o-mini"
    assert persona_llm.openai_api_base == "https://api.openai.com/v1"
    assert persona_llm.openai_api_key.get_secret_value() == "sk-test"
    assert persona_llm.temperature == 0.7
    assert judge_llm.temperature == 0.0


def test_get_llm_raises_when_no_model_configured():
    AgentModelConfig.get_solo()

    with pytest.raises(ModelNotConfigured):
        get_llm(ModelPurpose.PERSONA)


def test_get_llm_raises_when_model_inactive():
    model = _make_model(model_active=False)
    config = AgentModelConfig.get_solo()
    config.persona_model = model
    config.save()

    with pytest.raises(ModelNotConfigured):
        get_llm(ModelPurpose.PERSONA)


def test_get_llm_raises_when_provider_inactive():
    model = _make_model(provider_active=False)
    config = AgentModelConfig.get_solo()
    config.judge_model = model
    config.save()

    with pytest.raises(ModelNotConfigured):
        get_llm(ModelPurpose.JUDGE)


@dataclass
class _Schema:
    value: str = "default"


def test_get_structured_llm_uses_tool_strategy(monkeypatch):
    """`ToolStrategy` via `create_agent` é o único caminho que devolveu sempre um
    objeto bem formado em teste real contra este provedor e modelo: `ProviderStrategy`
    (saída estruturada nativa) falhou em todas as tentativas, e
    `ChatOpenAI.with_structured_output` nos três métodos já devolveu texto solto,
    `None`, ou objeto com campo obrigatório ausente.
    """
    model = _make_model()
    config = AgentModelConfig.get_solo()
    config.persona_model = model
    config.save()

    captured = {}

    class _FakeAgent:
        def invoke(self, payload):
            captured["messages"] = payload["messages"]
            return {"structured_response": _Schema("from-agent")}

    def fake_create_agent(*, model, tools, response_format):
        captured["model"] = model
        captured["tools"] = tools
        captured["response_format"] = response_format
        return _FakeAgent()

    monkeypatch.setattr("apps.llm.services.factory.create_agent", fake_create_agent)

    structured_llm = factory.get_structured_llm(ModelPurpose.PERSONA, _Schema)
    result = structured_llm.invoke(["a message"])

    assert result == _Schema("from-agent")
    assert captured["tools"] == []
    assert captured["messages"] == ["a message"]
    assert isinstance(captured["response_format"], factory.ToolStrategy)


def test_get_structured_llm_falls_back_to_empty_schema_when_agent_returns_nothing(
    monkeypatch,
):
    model = _make_model()
    config = AgentModelConfig.get_solo()
    config.persona_model = model
    config.save()

    class _FakeAgent:
        def invoke(self, payload):
            return {"structured_response": None}

    monkeypatch.setattr(
        "apps.llm.services.factory.create_agent",
        lambda **kwargs: _FakeAgent(),
    )

    structured_llm = factory.get_structured_llm(ModelPurpose.PERSONA, _Schema)
    result = structured_llm.invoke(["a message"])

    assert result == _Schema()
