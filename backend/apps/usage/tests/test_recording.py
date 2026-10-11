from decimal import Decimal
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from openai import BadRequestError

from apps.agents.services.schemas import PersonaTurn
from apps.llm.constants import ModelCategory, ModelPurpose
from apps.llm.models import LLMModel, LLMProvider
from apps.llm.services.factory import AudioClient, _StructuredAgent
from apps.usage.constants import UsagePurpose
from apps.usage.models import ModelUsage
from apps.usage.services import recording
from apps.usage.services.owner import usage_owner
from apps.voice.services import stt, tts

pytestmark = pytest.mark.django_db


@pytest.fixture
def provider():
    return LLMProvider.objects.create(
        code="groq", name="Groq", base_url="https://api.groq.com/openai/v1", api_key_env="LLM_TEST_API_KEY"
    )


def _model(provider, category=ModelCategory.CHAT, **fields) -> LLMModel:
    return LLMModel.objects.create(
        provider=provider,
        category=category,
        model_id=f"m-{category}",
        display_name="m",
        **fields,
    )


@pytest.fixture
def chat_model(provider):
    return _model(
        provider,
        input_price_per_million_tokens=Decimal("0.10"),
        output_price_per_million_tokens=Decimal("0.50"),
    )


def _reply(input_tokens: int, output_tokens: int) -> AIMessage:
    return AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


class _FakeAgent:
    def __init__(self, *outcomes):
        self._outcomes = list(outcomes)

    def invoke(self, payload):
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return {"messages": [*payload["messages"], *outcome[0]], "structured_response": outcome[1]}


def _agent(model, *outcomes) -> _StructuredAgent:
    return _StructuredAgent(_FakeAgent(*outcomes), PersonaTurn, ModelPurpose.PERSONA, model)


def _refusal() -> BadRequestError:
    import httpx

    response = httpx.Response(400, request=httpx.Request("POST", "https://x"))
    return BadRequestError(
        "recusa", response=response, body={"code": "tool_use_failed", "failed_generation": "x"}
    )


def test_a_chat_call_records_the_tokens_the_owner_and_the_cost(chat_model, django_user_model):
    user = django_user_model.objects.create_user(username="maria")
    turn = PersonaTurn(line="Hi")
    agent = _agent(chat_model, ([_reply(1000, 200)], turn))

    with usage_owner(user=user):
        result = agent.invoke([HumanMessage(content="oi")])

    assert result == turn
    usage = ModelUsage.objects.get()
    assert (usage.user, usage.username_at_time) == (user, "maria")
    assert usage.purpose == UsagePurpose.PERSONA
    assert (usage.input_tokens, usage.output_tokens, usage.model_calls) == (1000, 200, 1)
    assert usage.cost_usd == Decimal("0.0002")
    assert usage.priced is True
    assert usage.llm_model == chat_model and usage.model_id_at_time == chat_model.model_id
    assert not usage.failed


def test_a_retry_after_a_schema_refusal_is_summed_in_a_single_line(chat_model):
    turn = PersonaTurn(line="Hi")
    agent = _agent(chat_model, _refusal(), ([_reply(500, 100)], turn))

    agent.invoke([HumanMessage(content="oi")])

    usage = ModelUsage.objects.get()
    assert usage.model_calls == 2
    assert (usage.input_tokens, usage.output_tokens) == (500, 100)


def test_a_call_outside_any_owner_is_recorded_as_system_use(chat_model):
    _agent(chat_model, ([_reply(10, 5)], PersonaTurn(line="Hi"))).invoke(
        [HumanMessage(content="oi")]
    )

    usage = ModelUsage.objects.get()
    assert usage.user is None
    assert usage.username_at_time == ""
    assert usage.attempt is None and usage.review_item is None


def test_a_provider_failure_is_recorded_as_a_failed_line_and_still_propagates(chat_model):
    agent = _agent(chat_model, TimeoutError("provedor parado"))

    with pytest.raises(TimeoutError):
        agent.invoke([HumanMessage(content="oi")])

    usage = ModelUsage.objects.get()
    assert usage.failed is True
    assert usage.error_code == "TimeoutError"
    assert (usage.input_tokens, usage.output_tokens, usage.model_calls) == (0, 0, 0)
    assert usage.cost_usd == 0


def test_a_model_without_prices_is_recorded_with_zero_cost_and_not_priced(provider):
    model = _model(provider)

    _agent(model, ([_reply(10, 5)], PersonaTurn(line="Hi"))).invoke([HumanMessage(content="oi")])

    usage = ModelUsage.objects.get()
    assert usage.cost_usd == 0
    assert usage.priced is False
    assert usage.input_tokens == 10


def test_a_failure_while_saving_the_usage_never_breaks_the_call(chat_model, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(ModelUsage.objects, "create", broken)
    turn = PersonaTurn(line="Hi")

    result = _agent(chat_model, ([_reply(10, 5)], turn)).invoke([HumanMessage(content="oi")])

    assert result == turn


def test_a_failure_while_saving_does_not_poison_the_callers_transaction(
    chat_model, django_user_model, monkeypatch
):
    from django.db import transaction

    monkeypatch.setattr(recording, "ModelUsage", SimpleNamespace(objects=SimpleNamespace(
        create=lambda **kwargs: ModelUsage.objects.create(purpose="invalido" * 10)
    )))

    with transaction.atomic():
        recording.record_chat_call(
            llm_model=chat_model,
            purpose="persona",
            input_tokens=1,
            output_tokens=1,
            model_calls=1,
            duration_ms=1,
        )
        django_user_model.objects.create_user(username="ainda-funciona")

    assert django_user_model.objects.filter(username="ainda-funciona").exists()


class _Transcriptions:
    def __init__(self, response=None, error=None):
        self._response, self._error = response, error

    def create(self, **kwargs):
        if self._error:
            raise self._error
        return self._response


def _stt_client(monkeypatch, model, response=None, error=None):
    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=_Transcriptions(response, error)))
    monkeypatch.setattr(
        stt, "get_audio_client", lambda purpose: AudioClient(client, model.model_id, model)
    )


def test_a_transcription_records_the_duration_and_the_billed_minimum(provider, monkeypatch):
    model = _model(
        provider, ModelCategory.STT, price_per_audio_hour=Decimal("0.04"),
        min_billed_audio_seconds=10,
    )
    _stt_client(monkeypatch, model, SimpleNamespace(text="  hello ", duration=3.0))

    text = stt.transcribe(b"audio")

    assert text == "hello"
    usage = ModelUsage.objects.get()
    assert usage.purpose == UsagePurpose.TRANSCRIPTION
    assert (usage.audio_seconds, usage.billed_audio_seconds) == (3.0, 10.0)
    assert usage.cost_usd == (Decimal(10) * Decimal("0.04") / Decimal(3600)).quantize(
        Decimal("0.00000001")
    )
    assert usage.priced is True


def test_a_transcription_without_duration_still_returns_the_text(provider, monkeypatch):
    model = _model(provider, ModelCategory.STT, price_per_audio_hour=Decimal("0.04"))
    _stt_client(monkeypatch, model, SimpleNamespace(text="hello"))

    assert stt.transcribe(b"audio") == "hello"

    usage = ModelUsage.objects.get()
    assert usage.audio_seconds is None
    assert usage.cost_usd == 0


def test_a_failed_transcription_is_recorded_and_propagates(provider, monkeypatch):
    model = _model(provider, ModelCategory.STT)
    _stt_client(monkeypatch, model, error=RuntimeError("provedor fora"))

    with pytest.raises(RuntimeError):
        stt.transcribe(b"audio")

    usage = ModelUsage.objects.get()
    assert usage.failed is True
    assert usage.error_code == "RuntimeError"


def test_the_speech_records_the_characters_sent(provider, monkeypatch):
    model = _model(provider, ModelCategory.TTS, price_per_million_characters=Decimal("22"))
    speech = SimpleNamespace(create=lambda **kwargs: SimpleNamespace(read=lambda: b"wav"))
    client = SimpleNamespace(audio=SimpleNamespace(speech=speech))
    monkeypatch.setattr(
        tts, "get_audio_client", lambda purpose: AudioClient(client, model.model_id, model)
    )

    audio = tts.synthesize("Hello there, welcome to the hotel.", "autumn")

    assert audio == b"wav"
    usage = ModelUsage.objects.get()
    assert usage.purpose == UsagePurpose.SPEECH
    assert usage.characters == len("Hello there, welcome to the hotel.")
    assert usage.cost_usd > 0 and usage.priced is True
