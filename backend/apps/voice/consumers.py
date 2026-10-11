import json
import logging
import re
import time
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import F
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.agents.graph.builder import build_scenario_graph
from apps.agents.graph.listen import listen_live
from apps.agents.services.session_runner import evaluate_and_record_attempt, resolve_execution
from apps.agents.services.transcript import AFTER_HINT_KEY
from apps.agents.services.tutor import suggest_answer
from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt
from apps.llm.services.factory import log_active_models
from apps.usage.services.owner import usage_owner
from apps.usage.services.session_limits import (
    SessionRefused,
    open_session_lease,
    release_session_lease,
    turn_audio_limit_bytes,
)
from apps.voice.services.failures import (
    FAILURE_DESCRIPTIONS,
    SessionErrorCode,
    classify_failure,
    is_invalid_audio,
)
from apps.voice.services.stt import transcribe
from apps.voice.services.tts import synthesize

_SPEAKER_PREFIX = re.compile(r"^\[([^\]]+)\]\s*(.*)$", re.DOTALL)

logger = logging.getLogger(__name__)


def _split_speaker(content: str) -> tuple[str, str]:
    match = _SPEAKER_PREFIX.match(content or "")
    if not match:
        return "", content or ""
    return match.group(1), match.group(2)


class LiveSessionConsumer(AsyncWebsocketConsumer):
    """Sessão de voz ao vivo de um cenário: um turno por vez, controlado pelo aluno.

    Sem channel layer: cada conexão é privada, sem grupos nem broadcast. O aluno se
    identifica pelo mesmo token de acesso JWT que a API HTTP usa (`?token=`), validado
    com `JWTAuthentication` — sem `AuthMiddlewareStack` do Channels, que exigiria sessão
    Django, mecanismo que este projeto não usa para a API.
    """

    async def connect(self) -> None:
        """Autentica o aluno, abre a tentativa e faz a persona abrir a cena.

        `?hints=1` na URL diz que o aluno ligou as dicas no briefing: só assim os pedidos
        de dica são atendidos, e a tentativa registra a escolha.
        """
        self.scene_over = False
        self.lease = None
        self.hints_enabled = False
        self.current_hint: str | None = None
        await self.accept()

        scenario_slug = self.scope["url_route"]["kwargs"]["scenario_slug"]
        level_order = self.scope["url_route"]["kwargs"]["level_order"]
        query = parse_qs(self.scope["query_string"].decode())
        token = (query.get("token") or [None])[0]
        hints_requested = (query.get("hints") or ["0"])[0] == "1"

        if not token:
            await self._fail("Parâmetro 'token' é obrigatório na URL.")
            return

        try:
            user = await sync_to_async(self._authenticate)(token)
        except AuthenticationFailed:
            await self._fail("Token inválido ou expirado.")
            return

        if user.must_change_password:
            await self._fail("Defina uma senha nova antes de iniciar uma sessão.")
            return

        try:
            self.lease = await sync_to_async(open_session_lease)(user)
        except SessionRefused as refusal:
            code = SessionErrorCode(refusal.code)
            await self._fail(FAILURE_DESCRIPTIONS[code], code=code)
            return

        try:
            content, memory, attempt = await sync_to_async(self._resolve_execution)(
                user, scenario_slug, level_order
            )
        except ObjectDoesNotExist as exc:
            await self._fail(str(exc))
            return

        self.user = user
        self.content = content
        self.attempt = attempt
        self.seen_messages = 0
        if hints_requested:
            await sync_to_async(
                Attempt.objects.filter(pk=attempt.pk).update
            )(hints_enabled=True)
            self.hints_enabled = True
        self.graph = build_scenario_graph(
            content, memory, listen_node=listen_live, checkpointer=MemorySaver()
        )
        self.thread_config = {"configurable": {"thread_id": str(attempt.pk)}}
        await sync_to_async(log_active_models)()

        initial_state = {
            "messages": [],
            "current_speaker": "",
            "turn_count": 0,
            "scene_resolved": False,
            "should_end": False,
            "taking_over": False,
            "addressed_by_student": False,
        }
        with self._usage_owner():
            await self._advance(initial_state, resume=None, started_at=time.monotonic())

    async def disconnect(self, code) -> None:
        """Libera a sessão reservada do aluno, por qualquer motivo que a conexão tenha terminado.

        Uma falha ao liberar vai para o log e não derruba o consumidor: a reserva vence sozinha
        depois do tempo máximo, então o pior caso é o aluno esperar, e não a conexão quebrar.
        """
        try:
            await sync_to_async(release_session_lease)(getattr(self, "lease", None))
        except Exception as exc:
            logger.error("falha ao liberar a sessão de voz reservada: %s", exc)

    def _usage_owner(self):
        """A marca de dono do uso de modelos: o aluno e a sessão desta conexão."""
        return usage_owner(user=self.user, attempt=self.attempt)

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        """Atende uma mensagem do cliente com o uso dos modelos atribuído ao aluno e à sessão."""
        with self._usage_owner():
            await self._receive(text_data, bytes_data)

    async def _receive(self, text_data: str | None, bytes_data: bytes | None) -> None:
        """Recebe o áudio de um turno do aluno, transcreve e avança a conversa.

        Falha do provedor de STT encerra a sessão com erro explícito, sem fallback
        silencioso. Transcrição vazia não avança nem encerra: o cliente recebe
        `no_speech` e a vez continua do aluno. O mesmo vale para um áudio que o provedor
        recusa por não ser um arquivo válido, como o de um toque curto demais: é um problema
        da gravação, e não do provedor. A transcrição só aparece no console do
        servidor — o cliente nunca a recebe, por decisão de produto (sessão ao vivo sem
        transcrição na tela).

        Depois do fim da cena, o áudio é ignorado antes mesmo de transcrever: os handlers
        rodam um de cada vez, então um áudio que chegou durante a avaliação só é
        processado depois dela, e retomá-lo avaliaria e gravaria a tentativa de novo.

        Mensagens de texto são pedidos do cliente; o único que existe é o pedido de dica.
        Quando o aluno viu uma dica nesta vez, a fala dele segue marcada para o grafo, e
        a dica da vez é esquecida: a próxima vez começa sem dica.
        """
        if bytes_data is None:
            if text_data is not None:
                await self._handle_client_message(text_data)
            return
        if self.scene_over:
            print("[session] audio recebido depois do fim da cena; ignorado")
            return
        if len(bytes_data) > await sync_to_async(turn_audio_limit_bytes)():
            print("[session] audio maior que o limite do turno; recusado sem transcrever")
            await self.send(text_data=json.dumps({"type": "audio_too_large"}))
            return

        started_at = time.monotonic()
        try:
            text = await sync_to_async(transcribe)(bytes_data)
        except Exception as exc:
            if is_invalid_audio(exc):
                print("[stt] audio invalido (gravacao curta demais); o aluno fala de novo")
                await self.send(text_data=json.dumps({"type": "no_speech"}))
                return
            await self._fail_with_error(exc)
            return
        print(f"[timing] stt: {time.monotonic() - started_at:.2f}s")

        if not text.strip():
            print("[stt] transcricao vazia; o aluno fala de novo, sem avancar a conversa")
            await self.send(text_data=json.dumps({"type": "no_speech"}))
            return

        print(f"You: {text}")

        resume = {"text": text, AFTER_HINT_KEY: True} if self.current_hint else text
        self.current_hint = None
        await self._advance(None, resume=resume, started_at=started_at)

    async def _handle_client_message(self, text_data: str) -> None:
        """Atende uma mensagem de texto do cliente; mensagens desconhecidas são ignoradas."""
        try:
            message = json.loads(text_data)
        except json.JSONDecodeError:
            return
        if isinstance(message, dict) and message.get("type") == "hint_request":
            await self._answer_hint_request()

    async def _answer_hint_request(self) -> None:
        """Manda ao aluno a dica da vez atual, gerando-a na primeira vez que ele pede.

        Só vale numa sessão aberta com as dicas ligadas e antes do fim da cena. A dica da
        vez fica guardada: pedir de novo devolve a mesma, sem nova chamada ao modelo nem
        nova contagem. Se o tutor falhar ou não produzir nada, o aluno é avisado de que a
        dica não está disponível e a sessão segue, porque a dica é um apoio, não uma etapa
        da conversa; nesse caso nada é contado.
        """
        if not self.hints_enabled or self.scene_over:
            return
        if self.current_hint is None:
            snapshot = await self.graph.aget_state(self.thread_config)
            history = list(snapshot.values.get("messages") or [])
            try:
                suggestion = await sync_to_async(suggest_answer)(self.content, history)
            except Exception as exc:
                logger.error("Dica não gerada", exc_info=exc)
                suggestion = ""
            if not suggestion:
                await self.send(text_data=json.dumps({"type": "hint_unavailable"}))
                return
            self.current_hint = suggestion
            await sync_to_async(
                Attempt.objects.filter(pk=self.attempt.pk).update
            )(hints_used=F("hints_used") + 1)
            print(f"[hint] {suggestion}")
        await self.send(text_data=json.dumps({"type": "hint", "text": self.current_hint}))

    async def _advance(
        self, initial_state: dict | None, *, resume: str | dict | None, started_at: float
    ) -> None:
        """Roda o grafo até a próxima pausa e fala as novas mensagens.

        `started_at` marca o início da rodada (a chegada do áudio do aluno, ou a conexão
        na abertura), para que o tempo total registrado inclua a transcrição.
        """
        try:
            if initial_state is not None:
                state = await self.graph.ainvoke(initial_state, config=self.thread_config)
            else:
                state = await self.graph.ainvoke(Command(resume=resume), config=self.thread_config)
        except Exception as exc:
            await self._fail_with_error(exc)
            return

        spoken = await self._speak_new_messages(state, started_at)
        if not spoken:
            return
        print(f"[timing] round total: {time.monotonic() - started_at:.2f}s")

        if "__interrupt__" not in state:
            await self._finish(state)

    async def _speak_new_messages(self, state: dict, started_at: float) -> bool:
        """Sintetiza e envia, em ordem, as falas novas das personas.

        Falha do provedor de TTS encerra a sessão com erro explícito, sem fallback de
        síntese local. Devolve `False` nesse caso — a sessão já foi encerrada e quem
        chamou não deve continuar.
        """
        messages = list(state.get("messages") or [])
        new_messages = messages[self.seen_messages :]
        self.seen_messages = len(messages)
        first_audio_sent = False

        for message in new_messages:
            if not isinstance(message, AIMessage):
                continue
            name, text = _split_speaker(message.content)
            role = next((r for r in self.content.roles if r.name == name), None)
            voice = role.voice if role else self.content.roles[0].voice
            synthesis_started_at = time.monotonic()
            try:
                audio = await sync_to_async(synthesize)(text, voice)
            except Exception as exc:
                await self._fail_with_error(exc)
                return False
            print(f"[timing] tts ({name}): {time.monotonic() - synthesis_started_at:.2f}s")
            await self.send(bytes_data=audio)
            if not first_audio_sent:
                first_audio_sent = True
                print(f"[timing] first audio sent after {time.monotonic() - started_at:.2f}s")
        return True

    async def _finish(self, state: dict) -> None:
        """Encerra a cena: avisa o cliente, avalia, grava a tentativa e manda o resultado.

        O aviso `evaluating` sai antes do avaliador, que leva dezenas de segundos: sem
        ele, o cliente devolvia a vez ao aluno ao terminar o último áudio, como se a
        conversa continuasse.
        """
        self.scene_over = True
        await self.send(text_data=json.dumps({"type": "evaluating"}))
        try:
            attempt = await sync_to_async(evaluate_and_record_attempt)(
                self.attempt, self.content, state
            )
        except Exception as exc:
            await self._fail_with_error(exc, SessionErrorCode.REPORT_FAILED)
            return
        await self.send(
            text_data=json.dumps(
                {
                    "type": "session_ended",
                    "attempt_id": attempt.pk,
                    "final_score": attempt.final_score,
                    "passed": attempt.passed,
                }
            )
        )
        await self.close()

    async def _fail(self, message: str, *, code: SessionErrorCode | None = None) -> None:
        """Encerra a sessão com um aviso de erro; `code` só vai quando a falha é de uma etapa."""
        self.scene_over = True
        payload = {"type": "error", "message": message}
        if code is not None:
            payload["code"] = code.value
        await self.send(text_data=json.dumps(payload))
        await self.close()

    async def _fail_with_error(
        self, exc: BaseException, code: SessionErrorCode | None = None
    ) -> None:
        """Encerra a sessão por uma falha de etapa (fala, transcrição, voz ou avaliação).

        A exceção completa, com a pilha, vai para o registro do servidor, e o cliente recebe
        só o código e uma descrição fixa: a mensagem do provedor traz o nome do modelo e os
        números de uso, e a conexão não pode simplesmente cair sem explicação. `code`
        explícito vale quando a fase já diz o que falhou (a avaliação); sem ele, o código
        sai da classificação da exceção.
        """
        code = code or classify_failure(exc)
        logger.error("Sessão encerrada por falha (%s)", code.value, exc_info=exc)
        await self._fail(FAILURE_DESCRIPTIONS[code], code=code)

    @staticmethod
    def _authenticate(raw_token: str):
        """Devolve o aluno dono do token de acesso, pela mesma autenticação da API HTTP.

        Ler só o `user_id` do token deixava um aluno desativado abrir a sessão até o token
        expirar. Usar `JWTAuthentication` faz as duas portas de entrada seguirem a mesma regra:
        recusa o token inválido ou expirado, o aluno que não existe mais e o desativado.
        """
        authentication = JWTAuthentication()
        return authentication.get_user(authentication.get_validated_token(raw_token))

    @staticmethod
    def _resolve_execution(user, scenario_slug: str, level_order: int):
        scenario = Scenario.objects.get(slug=scenario_slug)
        level = Level.objects.get(order=level_order)
        return resolve_execution(scenario, level, user)
