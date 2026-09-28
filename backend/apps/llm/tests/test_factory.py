from dataclasses import dataclass

import httpx
import openai
import pytest

from apps.llm.constants import ModelCategory, ModelPurpose
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


def _make_audio_model(
    *,
    category: str,
    model_id: str,
    provider: LLMProvider | None = None,
    provider_active: bool = True,
    model_active: bool = True,
) -> LLMModel:
    if provider is None:
        provider = LLMProvider.objects.create(
            code=f"groq-{model_id}",
            name="Groq",
            base_url="https://api.groq.com/openai/v1",
            api_key="gsk-test",
            is_active=provider_active,
        )
    return LLMModel.objects.create(
        provider=provider,
        category=category,
        model_id=model_id,
        display_name=model_id,
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

    calls = []

    class _FakeAgent:
        def invoke(self, payload):
            calls.append(payload)
            return {"structured_response": None}

    monkeypatch.setattr(
        "apps.llm.services.factory.create_agent",
        lambda **kwargs: _FakeAgent(),
    )

    structured_llm = factory.get_structured_llm(ModelPurpose.PERSONA, _Schema)
    result = structured_llm.invoke(["a message"])

    assert result == _Schema()
    assert len(calls) == 2


def test_get_structured_llm_retries_once_when_first_response_has_no_schema(monkeypatch):
    model = _make_model()
    config = AgentModelConfig.get_solo()
    config.persona_model = model
    config.save()

    responses = iter([{"structured_response": None}, {"structured_response": _Schema("ok")}])

    class _FakeAgent:
        def invoke(self, payload):
            return next(responses)

    monkeypatch.setattr(
        "apps.llm.services.factory.create_agent",
        lambda **kwargs: _FakeAgent(),
    )

    structured_llm = factory.get_structured_llm(ModelPurpose.PERSONA, _Schema)
    result = structured_llm.invoke(["a message"])

    assert result == _Schema("ok")


def _provider_error(code: str) -> openai.BadRequestError:
    response = httpx.Response(400, request=httpx.Request("POST", "https://provider.test"))
    body = {"message": "rejected", "type": "invalid_request_error", "code": code}
    return openai.BadRequestError("Error code: 400", response=response, body=body)


def _structured_llm_with(monkeypatch, outcomes: list):
    model = _make_model()
    config = AgentModelConfig.get_solo()
    config.persona_model = model
    config.save()

    pending = iter(outcomes)

    class _FakeAgent:
        def invoke(self, payload):
            outcome = next(pending)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(
        "apps.llm.services.factory.create_agent",
        lambda **kwargs: _FakeAgent(),
    )
    return factory.get_structured_llm(ModelPurpose.PERSONA, _Schema)


def test_get_structured_llm_retries_when_provider_refuses_output_outside_schema(monkeypatch):
    structured_llm = _structured_llm_with(
        monkeypatch,
        [_provider_error("tool_use_failed"), {"structured_response": _Schema("ok")}],
    )

    assert structured_llm.invoke(["a message"]) == _Schema("ok")


def test_get_structured_llm_returns_empty_schema_when_provider_refuses_twice(monkeypatch):
    structured_llm = _structured_llm_with(
        monkeypatch,
        [_provider_error("tool_use_failed"), _provider_error("output_parse_failed")],
    )

    assert structured_llm.invoke(["a message"]) == _Schema()


def test_get_structured_llm_propagates_other_provider_errors(monkeypatch):
    structured_llm = _structured_llm_with(monkeypatch, [_provider_error("invalid_api_key")])

    with pytest.raises(openai.BadRequestError):
        structured_llm.invoke(["a message"])


def test_get_audio_client_builds_client_with_configured_parameters():
    stt_model = _make_audio_model(category=ModelCategory.STT, model_id="whisper-large-v3-turbo")
    tts_model = _make_audio_model(
        category=ModelCategory.TTS, model_id="canopylabs/orpheus-v1-english"
    )
    config = AgentModelConfig.get_solo()
    config.stt_model = stt_model
    config.tts_model = tts_model
    config.save()

    stt = factory.get_audio_client(ModelCategory.STT)
    tts = factory.get_audio_client(ModelCategory.TTS)

    assert stt.model_id == "whisper-large-v3-turbo"
    assert tts.model_id == "canopylabs/orpheus-v1-english"
    assert isinstance(stt.client, factory.OpenAI)
    assert isinstance(tts.client, factory.OpenAI)
    assert str(stt.client.base_url).rstrip("/") == "https://api.groq.com/openai/v1"


def test_get_audio_client_raises_when_no_model_configured():
    AgentModelConfig.get_solo()

    with pytest.raises(ModelNotConfigured):
        factory.get_audio_client(ModelCategory.STT)


def test_get_audio_client_raises_when_model_inactive():
    model = _make_audio_model(category=ModelCategory.TTS, model_id="orpheus", model_active=False)
    config = AgentModelConfig.get_solo()
    config.tts_model = model
    config.save()

    with pytest.raises(ModelNotConfigured):
        factory.get_audio_client(ModelCategory.TTS)


def test_get_audio_client_raises_when_provider_inactive():
    model = _make_audio_model(category=ModelCategory.STT, model_id="whisper", provider_active=False)
    config = AgentModelConfig.get_solo()
    config.stt_model = model
    config.save()

    with pytest.raises(ModelNotConfigured):
        factory.get_audio_client(ModelCategory.STT)
