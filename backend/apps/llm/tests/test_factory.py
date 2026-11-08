import socket
import threading
import time
from dataclasses import dataclass

import httpx
import openai
import pytest
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.completion_usage import CompletionUsage

from apps.llm.constants import ModelCategory, ModelPurpose, StructuredOutputMethod
from apps.llm.models import AgentModelConfig, LLMModel, LLMProvider
from apps.llm.services import factory
from apps.llm.services.factory import ModelNotConfigured, get_llm
from apps.voice.services.failures import SessionErrorCode, classify_failure

pytestmark = pytest.mark.django_db


def _make_model(
    *,
    provider_active: bool = True,
    model_active: bool = True,
    structured_output_method: str = StructuredOutputMethod.TOOL_CALLING,
    api_key: str = "test-key",
) -> LLMModel:
    provider = LLMProvider.objects.create(
        code="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key=api_key,
        is_active=provider_active,
    )
    return LLMModel.objects.create(
        provider=provider,
        model_id="gpt-4o-mini",
        display_name="GPT-4o mini",
        structured_output_method=structured_output_method,
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
            api_key="test-key",
            is_active=provider_active,
        )
    return LLMModel.objects.create(
        provider=provider,
        category=category,
        model_id=model_id,
        display_name=model_id,
        is_active=model_active,
    )


def test_get_llm_builds_client_with_configured_parameters(monkeypatch):
    model = _make_model(api_key="sk-test")
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


def test_only_the_judge_gets_its_own_output_limit(monkeypatch):
    model = _make_model(api_key="sk-test")
    config = AgentModelConfig.get_solo()
    config.persona_model = model
    config.judge_model = model
    config.router_model = model
    config.save()

    assert get_llm(ModelPurpose.JUDGE).max_tokens == 8192
    assert get_llm(ModelPurpose.PERSONA).max_tokens is None
    assert get_llm(ModelPurpose.ROUTER).max_tokens is None


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


def _captured_response_format(monkeypatch, method: str):
    model = _make_model(structured_output_method=method)
    config = AgentModelConfig.get_solo()
    config.persona_model = model
    config.save()

    captured = {}

    def fake_create_agent(*, model, tools, response_format):
        captured["response_format"] = response_format
        return object()

    monkeypatch.setattr("apps.llm.services.factory.create_agent", fake_create_agent)
    factory.get_structured_llm(ModelPurpose.PERSONA, _Schema)
    return captured["response_format"]


def test_new_model_defaults_to_tool_calling():
    assert _make_model().structured_output_method == StructuredOutputMethod.TOOL_CALLING


def test_tool_calling_model_uses_tool_strategy(monkeypatch):
    response_format = _captured_response_format(monkeypatch, StructuredOutputMethod.TOOL_CALLING)

    assert isinstance(response_format, factory.ToolStrategy)


def test_strict_model_uses_provider_strategy_with_strict_schema(monkeypatch):
    response_format = _captured_response_format(
        monkeypatch, StructuredOutputMethod.JSON_SCHEMA_STRICT
    )

    assert isinstance(response_format, factory.ProviderStrategy)
    assert response_format.schema_spec.strict is True


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


def test_get_structured_llm_retries_when_the_generated_json_does_not_validate(monkeypatch):
    structured_llm = _structured_llm_with(
        monkeypatch,
        [_provider_error("json_validate_failed"), {"structured_response": _Schema("ok")}],
    )

    assert structured_llm.invoke(["a message"]) == _Schema("ok")


def test_get_structured_llm_returns_empty_schema_when_the_json_never_validates(monkeypatch):
    structured_llm = _structured_llm_with(
        monkeypatch,
        [_provider_error("json_validate_failed"), _provider_error("json_validate_failed")],
    )

    assert structured_llm.invoke(["a message"]) == _Schema()


def _cut_off_error() -> openai.LengthFinishReasonError:
    completion = ChatCompletion(
        id="cut",
        created=0,
        model="gpt-oss-120b",
        object="chat.completion",
        choices=[
            Choice(
                index=0,
                finish_reason="length",
                message=ChatCompletionMessage(role="assistant", content=""),
            )
        ],
        usage=CompletionUsage(prompt_tokens=3897, completion_tokens=3072, total_tokens=6969),
    )
    return openai.LengthFinishReasonError(completion=completion)


def test_get_structured_llm_retries_when_the_response_is_cut_off_at_the_limit(monkeypatch):
    structured_llm = _structured_llm_with(
        monkeypatch,
        [_cut_off_error(), {"structured_response": _Schema("ok")}],
    )

    assert structured_llm.invoke(["a message"]) == _Schema("ok")


def test_get_structured_llm_returns_empty_schema_when_the_response_is_cut_off_twice(
    monkeypatch,
):
    structured_llm = _structured_llm_with(monkeypatch, [_cut_off_error(), _cut_off_error()])

    assert structured_llm.invoke(["a message"]) == _Schema()


def test_a_cut_off_response_counts_the_billed_tokens():
    tally = factory._Tally()

    tally.add_cut_off(_cut_off_error())

    assert (tally.model_calls, tally.input_tokens, tally.output_tokens) == (1, 3897, 3072)


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


class _SilentServer:
    """Servidor local que aceita a conexão e nunca responde, como um provedor travado."""

    def __init__(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen(8)
        self._connections: list[socket.socket] = []
        self._thread = threading.Thread(target=self._accept, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._socket.getsockname()[1]}/v1"

    def _accept(self) -> None:
        while True:
            try:
                connection, _ = self._socket.accept()
            except OSError:
                return
            self._connections.append(connection)

    def close(self) -> None:
        self._socket.close()
        for connection in self._connections:
            connection.close()


@pytest.fixture
def silent_provider(monkeypatch):
    server = _SilentServer()
    monkeypatch.setattr(factory, "PROVIDER_TIMEOUT_SECONDS", 0.4)
    monkeypatch.setattr(factory, "PROVIDER_MAX_RETRIES", 0)
    yield server
    server.close()


def _configure_silent(server: _SilentServer) -> LLMProvider:
    provider = LLMProvider.objects.create(
        code="silent", name="Silent", base_url=server.base_url, api_key="test-key", is_active=True
    )
    config = AgentModelConfig.get_solo()
    config.persona_model = LLMModel.objects.create(
        provider=provider, model_id="m", display_name="m", is_active=True
    )
    config.stt_model = LLMModel.objects.create(
        provider=provider,
        category=ModelCategory.STT,
        model_id="stt",
        display_name="stt",
        is_active=True,
    )
    config.save()
    return provider


def test_a_chat_call_to_a_provider_that_never_answers_times_out(silent_provider):
    _configure_silent(silent_provider)
    started = time.monotonic()

    with pytest.raises(openai.APITimeoutError) as failure:
        get_llm(ModelPurpose.PERSONA).invoke("oi")

    assert time.monotonic() - started < 5
    assert classify_failure(failure.value) is SessionErrorCode.PROVIDER_UNAVAILABLE


def test_an_audio_call_to_a_provider_that_never_answers_times_out(silent_provider):
    _configure_silent(silent_provider)
    audio = factory.get_audio_client(ModelCategory.STT)
    started = time.monotonic()

    with pytest.raises(openai.APITimeoutError) as failure:
        audio.client.audio.transcriptions.create(model=audio.model_id, file=("a.webm", b"x"))

    assert time.monotonic() - started < 5
    assert classify_failure(failure.value) is SessionErrorCode.PROVIDER_UNAVAILABLE


def test_the_default_limits_bound_a_stuck_call_to_about_a_minute():
    assert factory.PROVIDER_TIMEOUT_SECONDS == 30
    assert factory.PROVIDER_MAX_RETRIES == 1
    worst_case = factory.PROVIDER_TIMEOUT_SECONDS * (factory.PROVIDER_MAX_RETRIES + 1)
    assert worst_case <= 60


def test_the_clients_are_built_with_the_limits():
    model = _make_model()
    audio = _make_audio_model(category=ModelCategory.STT, model_id="whisper")
    config = AgentModelConfig.get_solo()
    config.persona_model = model
    config.stt_model = audio
    config.save()

    chat = get_llm(ModelPurpose.PERSONA)
    stt = factory.get_audio_client(ModelCategory.STT)

    assert chat.request_timeout == factory.PROVIDER_TIMEOUT_SECONDS
    assert chat.max_retries == factory.PROVIDER_MAX_RETRIES
    assert stt.client.timeout == factory.PROVIDER_TIMEOUT_SECONDS
    assert stt.client.max_retries == factory.PROVIDER_MAX_RETRIES


def test_a_stuck_call_is_retried_once_before_giving_up(silent_provider, monkeypatch):
    monkeypatch.setattr(factory, "PROVIDER_MAX_RETRIES", 1)
    _configure_silent(silent_provider)
    started = time.monotonic()

    with pytest.raises(openai.APITimeoutError):
        get_llm(ModelPurpose.PERSONA).invoke("oi")

    elapsed = time.monotonic() - started
    assert 0.8 <= elapsed < 5


def _configure_chat_and_stt(api_key: str = "test-key"):
    model = _make_model(api_key=api_key)
    audio = _make_audio_model(category=ModelCategory.STT, model_id="whisper")
    audio.provider.api_key = api_key
    audio.provider.save()
    config = AgentModelConfig.get_solo()
    config.persona_model = model
    config.stt_model = audio
    config.save()
    return model, audio


def test_the_chat_key_is_the_one_registered_on_the_provider():
    _configure_chat_and_stt(api_key="chave-do-admin")

    llm = get_llm(ModelPurpose.PERSONA)

    assert llm.openai_api_key.get_secret_value() == "chave-do-admin"


def test_the_audio_key_is_the_one_registered_on_the_provider():
    _configure_chat_and_stt(api_key="chave-do-admin")

    audio = factory.get_audio_client(ModelCategory.STT)

    assert audio.client.api_key == "chave-do-admin"


@pytest.mark.parametrize("value", ["", "   "])
def test_a_provider_without_a_key_is_not_configured_and_no_request_is_prepared(
    monkeypatch, value
):
    _configure_chat_and_stt(api_key=value)

    def must_not_build(*args, **kwargs):
        raise AssertionError("nenhum cliente pode ser montado sem a chave")

    monkeypatch.setattr(factory, "ChatOpenAI", must_not_build)
    monkeypatch.setattr(factory, "OpenAI", must_not_build)

    with pytest.raises(ModelNotConfigured) as chat_failure:
        get_llm(ModelPurpose.PERSONA)
    with pytest.raises(ModelNotConfigured) as audio_failure:
        factory.get_audio_client(ModelCategory.STT)

    for failure in (chat_failure, audio_failure):
        assert "admin" in str(failure.value)
        assert "groq" in str(failure.value) or "openai" in str(failure.value)


def test_a_key_that_no_longer_opens_is_not_configured(settings):
    settings.SECRET_KEY = "uma-chave-secreta"
    _configure_chat_and_stt(api_key="gsk_antiga")

    settings.SECRET_KEY = "outra-chave-secreta"

    with pytest.raises(ModelNotConfigured):
        get_llm(ModelPurpose.PERSONA)


def test_the_error_never_carries_a_key_value(settings):
    settings.SECRET_KEY = "uma-chave-secreta"
    _configure_chat_and_stt(api_key="gsk_VALOR-ANTIGO")
    settings.SECRET_KEY = "outra-chave-secreta"

    with pytest.raises(ModelNotConfigured) as failure:
        get_llm(ModelPurpose.PERSONA)

    assert "VALOR-ANTIGO" not in str(failure.value)
    assert "gsk_" not in str(failure.value)


def test_changing_the_key_in_the_provider_changes_the_next_call():
    model, _ = _configure_chat_and_stt(api_key="primeira")
    first = get_llm(ModelPurpose.PERSONA)

    model.provider.api_key = "segunda"
    model.provider.save()
    second = get_llm(ModelPurpose.PERSONA)

    assert first.openai_api_key.get_secret_value() == "primeira"
    assert second.openai_api_key.get_secret_value() == "segunda"


def test_a_provider_without_a_key_is_an_unavailable_service_for_the_student():
    _configure_chat_and_stt(api_key="")

    with pytest.raises(ModelNotConfigured) as failure:
        get_llm(ModelPurpose.PERSONA)

    assert classify_failure(failure.value) is SessionErrorCode.PROVIDER_UNAVAILABLE
