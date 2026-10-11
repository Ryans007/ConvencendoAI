import json
from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from channels.routing import URLRouter
from langchain_core.messages import AIMessage
from rest_framework_simplejwt.tokens import AccessToken

from apps.agents.graph import personas as graph_personas
from apps.agents.graph import routing as graph_routing
from apps.agents.services import evaluator
from apps.agents.services.schemas import (
    DimensionScores,
    EvaluationResult,
    PersonaTurn,
    RoutingDecision,
)
from apps.catalog.models import Level, Scenario
from apps.llm.constants import ModelCategory
from apps.llm.models import LLMModel, LLMProvider
from apps.llm.services.factory import AudioClient, _StructuredAgent
from apps.progress.models import Attempt
from apps.review.services import listening
from apps.usage.constants import UsagePurpose
from apps.usage.models import ModelUsage
from apps.usage.services.recording import record_speech_call, record_transcription_call
from apps.voice import consumers as voice_consumers
from apps.voice.routing import websocket_urlpatterns
from apps.voice.tests.session_client import SessionCommunicator
from apps.voice.services import stt, tts

pytestmark = pytest.mark.django_db


def _reply() -> AIMessage:
    return AIMessage(
        content="ok",
        usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
    )


class _SequenceAgent:
    """Agente falso que devolve cada resposta na ordem e repete a última."""

    def __init__(self, *structured):
        self._structured = list(structured)

    def invoke(self, payload):
        item = self._structured.pop(0) if len(self._structured) > 1 else self._structured[0]
        return {"messages": [*payload["messages"], _reply()], "structured_response": item}


def _agent(model, purpose, schema, *structured) -> _StructuredAgent:
    return _StructuredAgent(_SequenceAgent(*structured), schema, purpose, model)


def _fake_audio(monkeypatch, provider) -> None:
    stt_model = LLMModel.objects.create(
        provider=provider, category=ModelCategory.STT, model_id="whisper", display_name="w"
    )
    tts_model = LLMModel.objects.create(
        provider=provider, category=ModelCategory.TTS, model_id="orpheus", display_name="o"
    )
    transcriptions = SimpleNamespace(
        create=lambda **kw: SimpleNamespace(text="I need one more week.", duration=2.0)
    )
    speech = SimpleNamespace(create=lambda **kw: SimpleNamespace(read=lambda: b"wav"))
    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=transcriptions, speech=speech))
    monkeypatch.setattr(
        stt, "get_audio_client", lambda purpose: AudioClient(client, "whisper", stt_model)
    )
    monkeypatch.setattr(
        tts, "get_audio_client", lambda purpose: AudioClient(client, "orpheus", tts_model)
    )


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_every_model_call_of_a_live_session_is_attributed_to_the_student_and_the_attempt(
    django_user_model, monkeypatch
):
    user = django_user_model.objects.create(username="maria")
    other = django_user_model.objects.create(username="joao")
    token = str(AccessToken.for_user(user))
    provider = LLMProvider.objects.create(
        code="groq", name="Groq", base_url="https://x/v1", api_key="k"
    )
    chat = LLMModel.objects.create(provider=provider, model_id="chat", display_name="c")
    _fake_audio(monkeypatch, provider)
    monkeypatch.setattr(voice_consumers, "session_access_denial", lambda user, scenario, level: None)
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)

    persona = _agent(
        chat,
        "persona",
        PersonaTurn,
        PersonaTurn(line="Hello, let's talk about the deadline.", pass_to="student"),
        PersonaTurn(line="Understood, let's proceed.", pass_to="student", scene_resolved=True),
    )
    router = _agent(chat, "router", RoutingDecision, RoutingDecision(speaker=""))
    judge = _agent(
        chat,
        "judge",
        EvaluationResult,
        EvaluationResult(
            confirmed_criteria=["c1"],
            sub_scores=DimensionScores(
                fluency=10, vocabulary=5, grammar=10, pragmatics=10, autonomy=3
            ),
            feedback="Bom.",
        ),
    )
    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: persona)
    monkeypatch.setattr(graph_routing, "get_structured_llm", lambda purpose, schema: router)
    monkeypatch.setattr(evaluator, "get_structured_llm", lambda purpose, schema: judge)

    async def run() -> int:
        communicator = SessionCommunicator(
            URLRouter(websocket_urlpatterns),
            f"/ws/voice/{scenario.slug}/{level.order}/?token={token}",
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.receive_from()
        await communicator.send_to(bytes_data=b"raw-student-audio")
        await communicator.receive_from()
        assert json.loads(await communicator.receive_from()) == {"type": "evaluating"}
        ended = json.loads(await communicator.receive_from())
        assert ended["type"] == "session_ended"
        await communicator.disconnect()
        return ended["attempt_id"]

    attempt_id = async_to_sync(run)()

    usages = list(ModelUsage.objects.all())
    purposes = {usage.purpose for usage in usages}
    assert {
        UsagePurpose.PERSONA,
        UsagePurpose.ROUTER,
        UsagePurpose.JUDGE,
        UsagePurpose.TRANSCRIPTION,
        UsagePurpose.SPEECH,
    } <= purposes
    assert all(usage.user == user for usage in usages)
    assert all(usage.attempt_id == attempt_id for usage in usages)
    assert not ModelUsage.objects.filter(user=other).exists()
    assert Attempt.objects.get(pk=attempt_id).model_usages.count() == len(usages)


def test_a_review_answer_and_the_correct_form_audio_are_attributed_to_the_student_and_item(
    django_user_model, monkeypatch
):
    from django.utils import timezone

    from apps.review.models import ReviewAnswer, ReviewItem

    user = django_user_model.objects.create_user(username="maria")
    provider = LLMProvider.objects.create(
        code="groq", name="Groq", base_url="https://x/v1", api_key="k"
    )
    llm = LLMModel.objects.create(
        provider=provider, category=ModelCategory.TTS, model_id="orpheus", display_name="o"
    )
    item = ReviewItem.objects.create(user=user, rule="r", box=0, due_on=timezone.localdate())
    answer = ReviewAnswer.objects.create(
        item=item, step=1, attempt=1, heard="x", correct=True, feedback="f",
        revealed_correct="I worked there.",
    )

    def fake_synthesize(text, voice):
        record_speech_call(llm_model=llm, characters=len(text), duration_ms=1)
        return b"wav"

    monkeypatch.setattr(listening, "synthesize", fake_synthesize)

    listening.correct_form_audio(answer)

    usage = ModelUsage.objects.get()
    assert (usage.user, usage.review_item) == (user, item)
    assert usage.attempt is None


def test_a_review_transcription_is_attributed_to_the_student_and_item(
    django_user_model, monkeypatch
):
    from django.utils import timezone

    from apps.review.models import ReviewItem
    from apps.review.services import answering

    user = django_user_model.objects.create_user(username="maria")
    provider = LLMProvider.objects.create(
        code="groq", name="Groq", base_url="https://x/v1", api_key="k"
    )
    llm = LLMModel.objects.create(
        provider=provider, category=ModelCategory.STT, model_id="whisper", display_name="w"
    )
    item = ReviewItem.objects.create(user=user, rule="r", box=0, due_on=timezone.localdate())

    def fake_transcribe(audio):
        record_transcription_call(llm_model=llm, audio_seconds=2.0, duration_ms=1)
        return "   "

    monkeypatch.setattr(answering, "transcribe", fake_transcribe)

    result = answering.answer_item(item, b"audio", timezone.localdate())

    assert result.status == answering.AnswerStatus.NOT_HEARD
    usage = ModelUsage.objects.get()
    assert (usage.user, usage.review_item) == (user, item)


def test_a_call_made_by_a_command_is_system_use(django_user_model):
    provider = LLMProvider.objects.create(
        code="groq", name="Groq", base_url="https://x/v1", api_key="k"
    )
    llm = LLMModel.objects.create(
        provider=provider, category=ModelCategory.TTS, model_id="orpheus", display_name="o"
    )

    record_speech_call(llm_model=llm, characters=10, duration_ms=1)

    usage = ModelUsage.objects.get()
    assert usage.user is None and usage.attempt is None and usage.review_item is None
    assert str(usage).startswith("sistema")

