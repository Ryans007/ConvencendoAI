import asyncio
import contextlib
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
from apps.progress.choices import EndedBy
from apps.progress.models import Attempt
from apps.progress.services.session_access import AccessDenied, session_access_denial
from apps.progress.services.speech_turns import record_speech_turn, valid_wait_ms
from apps.llm.services.factory import log_active_models
from apps.llm.services.conversation_log import conversation_log
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
)
from apps.voice.services.stt import Transcription, transcribe_with_words
from apps.voice.services.tts import synthesize

_AUTH_TIMEOUT_SECONDS = 10
_AUTH_MAX_CHARS = 4096
_SPEAKER_PREFIX = re.compile(r"^\[([^\]]+)\]\s*(.*)$", re.DOTALL)
_PLAYBACK_REASON = re.compile(r"^[A-Za-z]{1,40}$")

logger = logging.getLogger(__name__)


def _split_speaker(content: str) -> tuple[str, str]:
    match = _SPEAKER_PREFIX.match(content or "")
    if not match:
        return "", content or ""
    return match.group(1), match.group(2)


class LiveSessionConsumer(AsyncWebsocketConsumer):
    """Sessão de voz ao vivo de um cenário: um turno por vez, controlado pelo aluno.

    Sem channel layer: cada conexão é privada, sem grupos nem broadcast. O aluno se
    identifica pelo mesmo token de acesso JWT que a API HTTP usa, mandado na primeira
    mensagem da conexão e validado com `JWTAuthentication` — sem `AuthMiddlewareStack`
    do Channels, que exigiria sessão Django, mecanismo que este projeto não usa na API.
    """

    async def connect(self) -> None:
        """Aceita a conexão e espera a mensagem de autenticação, sem iniciar nada ainda.

        O token não vem na URL, porque o log de acesso do servidor grava a URL inteira e o
        token ficaria lá em texto. O handshake do WebSocket não leva credencial, então a
        conexão é aceita e o aluno se identifica na primeira mensagem. Nada é gasto antes
        disso: nem a reserva da sessão, nem a tentativa, nem uma chamada a modelo. Se a
        mensagem não chega a tempo, a conexão é encerrada.
        """
        self.scene_over = False
        self.started = False
        self.lease = None
        self.user = None
        self.attempt = None
        self.hints_enabled = False
        self.ready = False
        self._start_task: asyncio.Task | None = None
        self.current_hint: str | None = None
        self.pending_wait_ms: int | None = None
        await self.accept()
        self._auth_deadline = asyncio.create_task(self._close_if_not_authenticated())

    async def _close_if_not_authenticated(self) -> None:
        """Encerra a conexão que não mandou a autenticação no prazo, sem iniciar a execução."""
        await asyncio.sleep(_AUTH_TIMEOUT_SECONDS)
        if not self.started and not self.scene_over:
            with contextlib.suppress(Exception):
                await self._fail("A autenticação da sessão não chegou a tempo.")

    def _cancel_auth_deadline(self) -> None:
        deadline = getattr(self, "_auth_deadline", None)
        if deadline is not None and deadline is not asyncio.current_task():
            deadline.cancel()

    async def _authenticate_first_message(
        self, text_data: str | None, bytes_data: bytes | None
    ) -> None:
        """Lê a primeira mensagem, que precisa ser a de autenticação, e então inicia a sessão.

        Antes da autenticação nada além dela é aceito: áudio, outro tipo de mensagem, um JSON
        inválido ou uma mensagem grande demais encerram a conexão. O limite de tamanho existe
        para o servidor não ler e processar um corpo qualquer de quem ainda não provou quem é.
        """
        self._cancel_auth_deadline()
        if bytes_data is not None or text_data is None:
            await self._fail("A primeira mensagem deve ser a de autenticação.")
            return
        if len(text_data) > _AUTH_MAX_CHARS:
            await self._fail("A mensagem de autenticação é grande demais.")
            return
        try:
            message = json.loads(text_data)
        except json.JSONDecodeError:
            await self._fail("A primeira mensagem deve ser a de autenticação.")
            return
        token = message.get("token") if isinstance(message, dict) else None
        if not isinstance(message, dict) or message.get("type") != "auth" or not token:
            await self._fail("A primeira mensagem deve ser a de autenticação com o token.")
            return
        if not isinstance(token, str):
            await self._fail("A primeira mensagem deve ser a de autenticação com o token.")
            return
        self.started = True
        self._start_task = asyncio.create_task(self._run_start_session(token))

    async def _run_start_session(self, token: str) -> None:
        """Roda a abertura da sessão como tarefa própria, para a queda da conexão poder cancelá-la.

        Os handlers de uma conexão rodam um de cada vez, então com a abertura dentro do handler de
        autenticação o aviso de queda só era atendido depois da fala de abertura, que leva
        segundos de modelo e de voz. Nesse intervalo a reserva da conexão já morta continuava
        valendo, e a conexão seguinte do mesmo aluno, como a que a tela refaz ao recarregar, era
        recusada por "já existe uma sessão aberta". Uma falha inesperada da abertura encerra a
        sessão com o erro de sempre, porque numa tarefa ela não chegaria a ninguém.
        """
        try:
            await self._start_session(token)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._fail_with_error(exc)
            return
        self.ready = True

    async def _open_lease(self, user):
        """Reserva a sessão do aluno sem perder a reserva se a abertura for cancelada no meio.

        A reserva é criada numa thread, e cancelar quem espera por ela não a interrompe: sem
        cuidado, a reserva nasceria depois do cancelamento, sem ninguém para liberá-la. Por
        isso, ao ser cancelada, a abertura espera a thread terminar e libera o que ela criou.
        """
        acquisition = asyncio.ensure_future(sync_to_async(open_session_lease)(user))
        try:
            return await asyncio.shield(acquisition)
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await sync_to_async(release_session_lease)(await acquisition)
            raise

    async def _start_session(self, token: str) -> None:
        """Autentica o aluno, confere a jornada e os limites, abre a tentativa e abre a cena.

        `?hints=1` na URL diz que o aluno ligou as dicas no briefing: só assim os pedidos
        de dica são atendidos, e a tentativa registra a escolha. É a única coisa que a URL
        ainda leva, e não é sensível.
        """
        scenario_slug = self.scope["url_route"]["kwargs"]["scenario_slug"]
        level_order = self.scope["url_route"]["kwargs"]["level_order"]
        query = parse_qs(self.scope["query_string"].decode())
        hints_requested = (query.get("hints") or ["0"])[0] == "1"

        try:
            user = await sync_to_async(self._authenticate)(token)
        except AuthenticationFailed:
            await self._fail("Token inválido ou expirado.")
            return

        if user.must_change_password:
            await self._fail("Defina uma senha nova antes de iniciar uma sessão.")
            return

        denial = await sync_to_async(self._access_denial)(user, scenario_slug, level_order)
        if denial is not None:
            code = SessionErrorCode(denial.code)
            await self._fail(
                FAILURE_DESCRIPTIONS[code],
                code=code,
                retry_after_seconds=denial.retry_after_seconds,
            )
            return

        try:
            self.lease = await self._open_lease(user)
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
            "hand_floor_to": "",
            "addressed_by_student": False,
            "redirect_to": "",
            "supporting_enters": "",
        }
        with self._usage_owner():
            await self._advance(initial_state, resume=None, started_at=time.monotonic())

    async def disconnect(self, code) -> None:
        """Libera a sessão reservada do aluno, por qualquer motivo que a conexão tenha terminado.

        Cancela também o prazo da autenticação, se ele ainda estava correndo, e a abertura da
        sessão, se a conexão caiu antes de ela terminar: a reserva é liberada na hora, e não
        depois de a fala de abertura ser gerada.

        Uma falha ao liberar vai para o log e não derruba o consumidor: a reserva vence sozinha
        depois do tempo máximo, então o pior caso é o aluno esperar, e não a conexão quebrar.
        """
        self._cancel_auth_deadline()
        start_task = getattr(self, "_start_task", None)
        if start_task is not None and not start_task.done():
            start_task.cancel()
            await asyncio.gather(start_task, return_exceptions=True)
        try:
            await sync_to_async(release_session_lease)(getattr(self, "lease", None))
        except Exception as exc:
            logger.error("falha ao liberar a sessão de voz reservada: %s", exc)

    def _usage_owner(self):
        """A marca de dono do uso de modelos: o aluno e a sessão desta conexão."""
        return usage_owner(user=self.user, attempt=self.attempt)

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        """Atende uma mensagem do cliente com o uso dos modelos atribuído ao aluno e à sessão.

        Enquanto a sessão não começou, a única mensagem aceita é a de autenticação, e enquanto
        ela abre, nada é atendido: o cliente só fala depois de ouvir a abertura.
        """
        if not self.started:
            await self._authenticate_first_message(text_data, bytes_data)
            return
        if not self.ready:
            print("[session] mensagem recebida antes de a sessão abrir; ignorada")
            return
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

        Cada áudio consome a espera que o cliente informou logo antes dele, e a vez transcrita
        é gravada com as medidas de fala. Gravar a vez é só medida: uma falha ali vai para o
        log e a conversa segue.
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

        waited_ms, self.pending_wait_ms = self.pending_wait_ms, None
        started_at = time.monotonic()
        try:
            transcription = await sync_to_async(transcribe_with_words)(bytes_data)
        except Exception as exc:
            await self._fail_with_error(exc)
            return
        print(f"[timing] stt: {time.monotonic() - started_at:.2f}s")
        text = transcription.text

        if not text.strip():
            print("[stt] transcricao vazia; o aluno fala de novo, sem avancar a conversa")
            await self.send(text_data=json.dumps({"type": "no_speech"}))
            return

        conversation_log("You", text)
        await self._record_speech_turn(transcription, waited_ms)

        resume = {"text": text, AFTER_HINT_KEY: True} if self.current_hint else text
        self.current_hint = None
        await self._advance(None, resume=resume, started_at=started_at)

    async def _handle_client_message(self, text_data: str) -> None:
        """Atende uma mensagem de texto do cliente; mensagens desconhecidas são ignoradas."""
        try:
            message = json.loads(text_data)
        except json.JSONDecodeError:
            return
        if not isinstance(message, dict):
            return
        if message.get("type") == "turn_timing":
            self.pending_wait_ms = valid_wait_ms(message.get("waited_ms"))
        elif message.get("type") == "hint_request":
            await self._answer_hint_request()
        elif message.get("type") == "playback_failed":
            self._log_playback_failure(message.get("reason"))
        elif message.get("type") == "end_session":
            await self._end_by_student()

    async def _record_speech_turn(
        self, transcription: Transcription, waited_ms: int | None
    ) -> None:
        """Grava a vez do aluno com as medidas de fala, sem nunca interromper a conversa."""
        try:
            await sync_to_async(record_speech_turn)(
                self.attempt,
                text=transcription.text,
                words=transcription.words,
                waited_ms=waited_ms,
                after_hint=self.current_hint is not None,
            )
        except Exception as exc:
            logger.error("falha ao gravar as medidas da vez de fala: %s", exc)

    async def _end_by_student(self) -> None:
        """Encerra a sessão a pedido do aluno: avalia a conversa até ali e grava a tentativa.

        Só vale depois de o aluno ter dado pelo menos uma resposta e antes do fim da cena. O
        pedido é atendido na vez do aluno, porque os handlers de uma conexão rodam um de cada
        vez: um pedido que chega durante uma rodada espera a rodada terminar. A conversa vem do
        estado pausado do grafo, o mesmo que o limite de turnos entregaria ao avaliador.
        """
        if self.scene_over:
            print("[session] pedido de encerramento depois do fim da cena; ignorado")
            return
        snapshot = await self.graph.aget_state(self.thread_config)
        messages = snapshot.values.get("messages") or []
        if not any(message.type == "human" for message in messages):
            print("[session] pedido de encerramento antes de qualquer resposta; ignorado")
            return
        await self._finish(dict(snapshot.values), EndedBy.STUDENT)

    @staticmethod
    def _log_playback_failure(reason: object) -> None:
        """Registra que o navegador do aluno recusou tocar uma fala, com o nome do erro.

        O console do celular não é acessível a quem mantém o sistema, então este é o único
        lugar onde a recusa aparece. O nome vem do cliente e só entra no log se for uma palavra
        curta de letras, para a conexão não servir de via para escrever texto livre no log.
        """
        valid = isinstance(reason, str) and _PLAYBACK_REASON.fullmatch(reason)
        print(f"[session] o navegador recusou tocar o audio: {reason if valid else 'desconhecido'}")

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
            conversation_log("[hint]", suggestion)
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

        Antes de cada áudio sai uma mensagem `speaker` com o nome de quem fala, para a tela dizer
        quem é: o nome é o único texto de uma fala que chega ao cliente, e nunca o que foi dito.
        O nome sai antes da síntese, e não junto do áudio, porque já é conhecido ali: enquanto o
        áudio é sintetizado, a tela mostra quem vai responder em vez de um texto genérico.

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
            speaker_name = role.name if role else name
            await self.send(text_data=json.dumps({"type": "speaker", "name": speaker_name}))
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

    async def _finish(self, state: dict, ended_by: str = EndedBy.TURN_LIMIT) -> None:
        """Encerra a cena: avisa o cliente, avalia, grava a tentativa e manda o resultado.

        `ended_by` diz como a sessão terminou e fica gravado na tentativa.

        O aviso `evaluating` sai antes do avaliador, que leva dezenas de segundos: sem
        ele, o cliente devolvia a vez ao aluno ao terminar o último áudio, como se a
        conversa continuasse.
        """
        self.scene_over = True
        await self.send(text_data=json.dumps({"type": "evaluating"}))
        try:
            attempt = await sync_to_async(evaluate_and_record_attempt)(
                self.attempt, self.content, state, ended_by
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

    async def _fail(
        self,
        message: str,
        *,
        code: SessionErrorCode | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        """Encerra a sessão com um aviso de erro; `code` só vai quando a falha é de uma etapa.

        `retry_after_seconds` vai junto quando a recusa tem um tempo de espera, como o
        intervalo entre tentativas de um nível.
        """
        self.scene_over = True
        payload = {"type": "error", "message": message}
        if code is not None:
            payload["code"] = code.value
        if retry_after_seconds is not None:
            payload["retry_after_seconds"] = retry_after_seconds
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
    def _access_denial(user, scenario_slug: str, level_order: int) -> AccessDenied | None:
        """Por que a jornada não libera esta sessão para o aluno, ou `None` se libera.

        Cenário ou nível inexistente não é recusa da jornada: segue o caminho de sempre, que
        responde que não existe.
        """
        try:
            scenario = Scenario.objects.get(slug=scenario_slug)
            level = Level.objects.get(order=level_order)
        except ObjectDoesNotExist:
            return None
        return session_access_denial(user, scenario, level)

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
