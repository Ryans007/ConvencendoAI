import json
import re
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.agents.graph.builder import build_scenario_graph
from apps.agents.graph.listen import listen_live
from apps.agents.services.session_runner import evaluate_and_record_attempt, resolve_execution
from apps.catalog.models import Level, Scenario
from apps.llm.services.factory import ModelNotConfigured
from apps.voice.services.stt import transcribe
from apps.voice.services.tts import synthesize

_SPEAKER_PREFIX = re.compile(r"^\[([^\]]+)\]\s*(.*)$", re.DOTALL)


def _split_speaker(content: str) -> tuple[str, str]:
    match = _SPEAKER_PREFIX.match(content or "")
    if not match:
        return "", content or ""
    return match.group(1), match.group(2)


class LiveSessionConsumer(AsyncWebsocketConsumer):
    """Sessão de voz ao vivo de um cenário: um turno por vez, controlado pelo aluno.

    Sem channel layer: cada conexão é privada, sem grupos nem broadcast. O aluno se
    identifica pelo mesmo token de acesso JWT que a API HTTP usa (`?token=`), validado
    diretamente com `AccessToken` — sem `AuthMiddlewareStack` do Channels, que exigiria
    sessão Django, mecanismo que este projeto não usa para a API.
    """

    async def connect(self) -> None:
        await self.accept()

        scenario_slug = self.scope["url_route"]["kwargs"]["scenario_slug"]
        level_order = self.scope["url_route"]["kwargs"]["level_order"]
        query = parse_qs(self.scope["query_string"].decode())
        token = (query.get("token") or [None])[0]

        if not token:
            await self._fail("Parâmetro 'token' é obrigatório na URL.")
            return

        try:
            user_id = AccessToken(token)["user_id"]
        except TokenError:
            await self._fail("Token inválido ou expirado.")
            return

        try:
            content, memory, attempt = await sync_to_async(self._resolve_execution)(
                user_id, scenario_slug, level_order
            )
        except ObjectDoesNotExist as exc:
            await self._fail(str(exc))
            return

        self.content = content
        self.attempt = attempt
        self.seen_messages = 0
        self.graph = build_scenario_graph(
            content, memory, listen_node=listen_live, checkpointer=MemorySaver()
        )
        self.thread_config = {"configurable": {"thread_id": str(attempt.pk)}}

        initial_state = {
            "messages": [],
            "current_speaker": "",
            "turn_count": 0,
            "scene_resolved": False,
            "should_end": False,
        }
        await self._advance(initial_state, resume=None)

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if bytes_data is None:
            return

        try:
            text = await sync_to_async(transcribe)(bytes_data)
        except Exception as exc:  # falha explícita do provedor de STT, sem fallback silencioso
            await self._fail(f"Falha na transcrição: {exc}")
            return

        # Só no console do servidor — o cliente nunca recebe a transcrição, por
        # decisão de produto (sessão ao vivo sem transcrição na tela).
        print(f"You: {text}")

        await self._advance(None, resume=text)

    async def _advance(self, initial_state: dict | None, *, resume: str | None) -> None:
        try:
            if initial_state is not None:
                state = await self.graph.ainvoke(initial_state, config=self.thread_config)
            else:
                state = await self.graph.ainvoke(Command(resume=resume), config=self.thread_config)
        except ModelNotConfigured as exc:
            await self._fail(str(exc))
            return

        await self._speak_new_messages(state)

        if "__interrupt__" not in state:
            await self._finish(state)

    async def _speak_new_messages(self, state: dict) -> None:
        messages = list(state.get("messages") or [])
        new_messages = messages[self.seen_messages :]
        self.seen_messages = len(messages)

        for message in new_messages:
            if not isinstance(message, AIMessage):
                continue
            name, text = _split_speaker(message.content)
            role = next((r for r in self.content.roles if r.name == name), None)
            voice = role.voice if role else self.content.roles[0].voice
            try:
                audio = await sync_to_async(synthesize)(text, voice)
            except Exception as exc:  # falha explícita do provedor de TTS, sem fallback local
                await self._fail(f"Falha na síntese de voz: {exc}")
                return
            await self.send(bytes_data=audio)

    async def _finish(self, state: dict) -> None:
        attempt = await sync_to_async(evaluate_and_record_attempt)(
            self.attempt, self.content, state
        )
        await self.send(
            text_data=json.dumps(
                {
                    "type": "session_ended",
                    "final_score": attempt.final_score,
                    "passed": attempt.passed,
                }
            )
        )
        await self.close()

    async def _fail(self, message: str) -> None:
        await self.send(text_data=json.dumps({"type": "error", "message": message}))
        await self.close()

    @staticmethod
    def _resolve_execution(user_id, scenario_slug: str, level_order: int):
        user = get_user_model().objects.get(pk=user_id)
        scenario = Scenario.objects.get(slug=scenario_slug)
        level = Level.objects.get(order=level_order)
        return resolve_execution(scenario, level, user)
