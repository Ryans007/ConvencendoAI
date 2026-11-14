import json
from dataclasses import dataclass, field

from asgiref.sync import async_to_sync
from channels.routing import URLRouter
from rest_framework_simplejwt.tokens import AccessToken

from apps.agents.graph import personas as graph_personas
from apps.agents.graph import routing as graph_routing
from apps.agents.services.evaluator import EvaluationOutcome, JudgedDimension
from apps.agents.services.schemas import PersonaTurn, RoutingDecision
from apps.voice import consumers as voice_consumers
from apps.voice.routing import websocket_urlpatterns
from apps.voice.services.stt import Transcription
from apps.voice.tests.session_client import SessionCommunicator

END_SESSION = json.dumps({"type": "end_session"})
STUDENT_TEXT = "I need one more week."


class ScriptedPersona:
    """Persona falsa que fala o roteiro, uma fala por chamada, e levanta as exceções do roteiro.

    Um passo que seja uma função é chamado na hora da fala e devolve o texto ou levanta, o que
    permite travar a geração de uma fala até o teste liberá-la.
    """

    def __init__(self, lines):
        self._lines = iter(lines)

    def invoke(self, messages):
        step = next(self._lines)
        if callable(step):
            step = step()
        if isinstance(step, BaseException):
            raise step
        return PersonaTurn(line=step, pass_to="student")


class FixedRouter:
    """Diretor de cena falso que devolve sempre a mesma decisão."""

    def __init__(self, decision: RoutingDecision):
        self._decision = decision

    def invoke(self, messages):
        return self._decision


@dataclass
class Installed:
    """O que os dublês gravaram: os textos sintetizados e as conversas entregues ao avaliador."""

    synthesized: list[str] = field(default_factory=list)
    evaluated: list[list[str]] = field(default_factory=list)


async def keep_the_test_connection() -> None:
    """Evita que o Channels feche a conexão do banco do teste a cada mensagem de texto."""


def install(monkeypatch, lines, routing: RoutingDecision, *, synthesize=None) -> Installed:
    """Troca modelos, transcrição, síntese e avaliador por dublês que deixam rastro.

    O áudio devolvido pela síntese é o próprio texto em bytes, para o teste saber qual fala
    cada áudio carrega. `synthesize` troca esse comportamento, para os testes de falha.
    """
    installed = Installed()
    monkeypatch.setattr("channels.consumer.aclose_old_connections", keep_the_test_connection)
    persona = ScriptedPersona(lines)
    router = FixedRouter(routing)
    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: persona)
    monkeypatch.setattr(graph_routing, "get_structured_llm", lambda purpose, schema: router)
    monkeypatch.setattr(
        voice_consumers, "transcribe_with_words", lambda audio: Transcription(STUDENT_TEXT)
    )

    def recording_synthesize(text, voice):
        installed.synthesized.append(text)
        if synthesize is not None:
            return synthesize(text, voice)
        return text.encode()

    monkeypatch.setattr(voice_consumers, "synthesize", recording_synthesize)

    def fake_evaluate(content, messages, known_rules=(), speech_metrics=None):
        installed.evaluated.append([message.content for message in messages])
        return EvaluationOutcome(
            confirmed_criteria=set(),
            judged_dimensions=[JudgedDimension(dimension="fluency", value=10, weight=15)],
            feedback="Ok.",
            memory_summary="Pediu mais prazo.",
            review_items=[],
        )

    monkeypatch.setattr("apps.agents.services.session_runner.evaluate", fake_evaluate)
    return installed


def student_token(django_user_model) -> str:
    user = django_user_model.objects.create(username="aluno")
    return str(AccessToken.for_user(user))


async def connect(
    token: str, slug: str = "negociar-prazo", *, hints: bool = False, stream_audio: bool = False
):
    """Abre a sessão como o frontend e devolve a conexão, ainda sem ter lido a abertura."""
    query = f"token={token}" + ("&hints=1" if hints else "")
    communicator = SessionCommunicator(
        URLRouter(websocket_urlpatterns), f"/ws/voice/{slug}/3/?{query}", stream_audio=stream_audio
    )
    connected, _ = await communicator.connect()
    assert connected
    return communicator


async def read_frames(communicator, audio_count: int) -> list:
    """Lê o que o aluno recebe até chegarem `audio_count` áudios, na ordem em que chegam.

    Mensagens de texto viram o JSON delas e cada áudio vira `("audio", texto)`, onde o texto é
    o que a síntese de teste recebeu.
    """
    frames: list = []
    audios = 0
    while audios < audio_count:
        raw = await communicator.receive_from()
        if isinstance(raw, bytes):
            frames.append(("audio", raw.decode()))
            audios += 1
        else:
            frames.append(json.loads(raw))
    return frames


def speaker(name: str) -> dict:
    return {"type": "speaker", "name": name}


def play_round(
    monkeypatch,
    django_user_model,
    lines,
    routing: RoutingDecision,
    *,
    slug: str = "negociar-prazo",
    audio_count: int,
) -> tuple[list, Installed]:
    """Joga uma rodada completa: abertura, uma resposta do aluno e o pedido de encerramento.

    Devolve o que o aluno recebeu na rodada depois da abertura e os rastros dos dublês, entre
    eles a conversa que o avaliador recebeu ao fim, que é a gravada na tentativa.
    """
    installed = install(monkeypatch, lines, routing)
    token = student_token(django_user_model)

    async def run() -> list:
        communicator = await connect(token, slug)
        await read_frames(communicator, 1)
        await communicator.send_to(bytes_data=b"student-audio")
        frames = await read_frames(communicator, audio_count)
        await communicator.send_to(text_data=END_SESSION)
        assert json.loads(await communicator.receive_from()) == {"type": "evaluating"}
        assert json.loads(await communicator.receive_from())["type"] == "session_ended"
        await communicator.disconnect()
        return frames

    return async_to_sync(run)(), installed
