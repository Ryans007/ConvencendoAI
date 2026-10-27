import time
from dataclasses import dataclass, field

from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy, ToolStrategy
from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI
from openai import BadRequestError, LengthFinishReasonError, OpenAI

from apps.llm.constants import (
    PROVIDER_MAX_RETRIES,
    PROVIDER_TIMEOUT_SECONDS,
    ModelCategory,
    ModelPurpose,
    StructuredOutputMethod,
)
from apps.llm.models import AgentModelConfig, LLMModel
from apps.llm.services.conversation_log import conversation_log
from apps.llm.services.model_override import current_override
from apps.usage.services.recording import record_chat_call

_TEMPERATURE_BY_PURPOSE = {
    ModelPurpose.PERSONA: 0.7,
    ModelPurpose.JUDGE: 0.0,
    ModelPurpose.ROUTER: 0.0,
}

_MAX_TOKENS_BY_PURPOSE = {
    ModelPurpose.JUDGE: 8192,
}

_FIELD_BY_PURPOSE = {
    ModelPurpose.PERSONA: "persona_model",
    ModelPurpose.JUDGE: "judge_model",
    ModelPurpose.ROUTER: "router_model",
}


class ModelNotConfigured(RuntimeError):
    """Nenhum modelo ativo está configurado para o papel pedido."""


def _require_key(model: LLMModel) -> LLMModel:
    """Recusa o modelo cujo provedor não tem a chave definida no ambiente do servidor.

    A chave vive só na variável de ambiente que o provedor nomeia. Sem ela, o modelo é tratado
    como não configurado, antes de montar qualquer cliente e de enviar qualquer pedido, e a
    mensagem diz qual variável falta, nunca um valor. A sessão e a revisão já tratam
    `ModelNotConfigured` como serviço de IA indisponível.
    """
    provider = model.provider
    if not provider.has_api_key:
        raise ModelNotConfigured(
            f"Provedor '{provider.code}' sem chave: defina a variável de ambiente "
            f"{provider.api_key_env}."
        )
    return model


def _model_for(purpose: str, config: AgentModelConfig) -> LLMModel:
    """O modelo do papel: o escolhido para a execução em curso, ou o da configuração gravada."""
    model = current_override(purpose) or getattr(config, _FIELD_BY_PURPOSE[purpose])
    if model is None or not model.is_active or not model.provider.is_active:
        raise ModelNotConfigured(
            f"Nenhum modelo ativo configurado para o papel '{purpose}'."
        )
    return _require_key(model)


def get_llm(purpose: str) -> ChatOpenAI:
    """Monta o cliente do papel pedido a partir do `AgentModelConfig` cadastrado.

    O cliente é sempre `ChatOpenAI`: nenhum provedor exige um SDK próprio, todos
    falam uma API compatível com a da OpenAI.

    Toda chamada tem limite de tempo e de retentativas. Sem eles valem os padrões do SDK, 10
    minutos por tentativa e 2 retentativas, e um provedor que aceita a conexão e não responde
    segurava a requisição por até 30 minutos, deixando a tela do aluno parada sem nunca
    falhar. Com 30 segundos e 1 retentativa, a chamada travada vira, em no máximo cerca de 1
    minuto, o erro de tempo esgotado que a sessão e a revisão já tratam como "serviço de IA
    indisponível". O SDK também retenta o tempo esgotado, por isso o pior caso é duas vezes o
    limite. As chamadas normais levam de 2 a 7 segundos, e 24 com o modelo frio.

    O avaliador tem limite de saída próprio, de 8192 tokens. Sem ele vale o padrão do
    provedor, e a Groq cortou uma avaliação em 3072 tokens, dos quais 2587 eram o raciocínio
    do modelo: a nota não chegou a ser escrita e o aluno ficou sem relatório. As avaliações
    com sucesso já chegaram a 2880 tokens. Os outros papéis escrevem respostas curtas e
    seguem com o padrão do provedor. O limite só é cobrado no que o modelo de fato gera.
    """
    config = AgentModelConfig.get_solo()
    model = _model_for(purpose, config)
    provider = model.provider
    return ChatOpenAI(
        model=model.model_id,
        api_key=provider.api_key,
        base_url=provider.base_url,
        temperature=_TEMPERATURE_BY_PURPOSE[purpose],
        max_tokens=_MAX_TOKENS_BY_PURPOSE.get(purpose),
        timeout=PROVIDER_TIMEOUT_SECONDS,
        max_retries=PROVIDER_MAX_RETRIES,
    )


@dataclass
class _Tally:
    """O consumo somado das respostas do modelo numa chamada do sistema."""

    input_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0
    started_at: float = field(default_factory=time.monotonic)

    def add(self, message: BaseMessage) -> None:
        usage = getattr(message, "usage_metadata", None) or {}
        self.input_tokens += int(usage.get("input_tokens", 0))
        self.output_tokens += int(usage.get("output_tokens", 0))

    def add_cut_off(self, error: LengthFinishReasonError) -> None:
        """Soma uma resposta cortada no limite de saída: ela não vira mensagem, mas foi cobrada."""
        self.model_calls += 1
        usage = error.completion.usage
        if usage is not None:
            self.input_tokens += usage.prompt_tokens
            self.output_tokens += usage.completion_tokens

    @property
    def duration_ms(self) -> int:
        return int((time.monotonic() - self.started_at) * 1000)


class _StructuredAgent:
    """Adapta um agente LangChain para a interface `.invoke(messages) -> schema` que o
    resto do código espera, sem expor o estado inteiro do agente (histórico, etc.).

    Cada chamada registra o tempo total e quantas vezes o modelo foi chamado: quando o
    modelo devolve uma resposta sem preencher o schema, o agente chama de novo por conta
    própria, e sem essa contagem as retentativas ficam escondidas dentro do tempo total.

    Se o agente terminar sem resposta estruturada, registra o que o modelo devolveu (para
    diagnosticar a causa) e tenta uma única vez mais. O limite é uma, para não voltar a
    esconder uma cadeia de retentativas dentro do tempo de uma fala.

    A recusa do provedor por saída fora do schema segue o mesmo caminho. Provedores que
    validam o schema no servidor, como a Groq, respondem HTTP 400 com os códigos de
    `_SCHEMA_REFUSAL_CODES` quando o modelo escreve texto em vez de preencher a estrutura;
    sem esse tratamento, a exceção atravessava o grafo e derrubava a sessão. Qualquer outro
    erro do provedor continua sendo propagado. O log da recusa inclui o que o modelo
    gerou (`failed_generation`, quando o provedor devolve), para diagnosticar a causa.

    A resposta cortada no limite de saída também é tentada de novo. Um modelo que raciocina
    antes de responder pode gastar o limite inteiro pensando e não chegar ao schema, e a
    biblioteca levanta `LengthFinishReasonError` em vez de devolver uma resposta vazia; sem
    esse tratamento, a avaliação do fim da sessão falhava e o aluno ficava sem relatório.
    """

    _ATTEMPTS = 2
    _SCHEMA_REFUSAL_CODES = frozenset(
        {"tool_use_failed", "output_parse_failed", "json_validate_failed"}
    )

    def __init__(self, agent, schema: type, purpose: str, model: LLMModel | None = None):
        self._agent = agent
        self._schema = schema
        self._purpose = purpose
        self._model = model

    def _log_missing_response(self, new_messages: list[BaseMessage]) -> None:
        last = next(
            (message for message in reversed(new_messages) if isinstance(message, AIMessage)),
            None,
        )
        if last is None:
            print(f"[warning] {self._purpose}: agente terminou sem nenhuma resposta do modelo")
            return
        tool_calls = [call.get("name") for call in last.tool_calls]
        print(f"[warning] {self._purpose}: resposta sem schema preenchido; tool_calls={tool_calls}")
        conversation_log(f"[warning] {self._purpose}: conteudo da resposta", str(last.content)[:200])

    def invoke(self, messages: list[BaseMessage]):
        """Chama o agente e devolve o schema preenchido, gravando o uso da chamada.

        A linha de uso soma o consumo de todas as respostas do modelo, inclusive as da nova
        tentativa, e é gravada também quando a chamada falha, antes de a exceção seguir.
        """
        tally = _Tally()
        try:
            structured = self._run(messages, tally)
        except Exception as exc:
            self._record(tally, failed=True, error_code=type(exc).__name__)
            raise
        self._record(tally)
        elapsed = time.monotonic() - tally.started_at
        print(f"[timing] {self._purpose}: {elapsed:.2f}s ({tally.model_calls} model call(s))")
        return structured or self._schema()

    def _record(self, tally: _Tally, *, failed: bool = False, error_code: str = "") -> None:
        if self._model is None:
            return
        record_chat_call(
            llm_model=self._model,
            purpose=self._purpose,
            input_tokens=tally.input_tokens,
            output_tokens=tally.output_tokens,
            model_calls=tally.model_calls,
            duration_ms=tally.duration_ms,
            failed=failed,
            error_code=error_code,
        )

    def _run(self, messages: list[BaseMessage], tally: _Tally):
        structured = None
        for _ in range(self._ATTEMPTS):
            try:
                result = self._agent.invoke({"messages": messages})
            except BadRequestError as exc:
                if exc.code not in self._SCHEMA_REFUSAL_CODES:
                    raise
                tally.model_calls += 1
                body = exc.body if isinstance(exc.body, dict) else {}
                generated = str(body.get("failed_generation", ""))[:200]
                print(
                    f"[warning] {self._purpose}: provedor recusou a resposta fora do schema "
                    f"({exc.code})"
                )
                conversation_log(f"[warning] {self._purpose}: gerado", generated)
                continue
            except LengthFinishReasonError as exc:
                tally.add_cut_off(exc)
                print(f"[warning] {self._purpose}: resposta cortada no limite de saída")
                continue
            new_messages = result.get("messages", [])[len(messages) :]
            for message in new_messages:
                if isinstance(message, AIMessage):
                    tally.model_calls += 1
                    tally.add(message)
            structured = result.get("structured_response")
            if structured is not None:
                break
            self._log_missing_response(new_messages)
        return structured


@dataclass(frozen=True)
class AudioClient:
    """Cliente de áudio já resolvido, com o identificador de modelo que a chamada exige.

    O cliente de áudio, ao contrário do `ChatOpenAI`, não recebe o modelo no construtor —
    cada chamada (`audio.transcriptions.create`, `audio.speech.create`) pede o `model` à
    parte.
    """

    client: OpenAI
    model_id: str
    model: LLMModel | None = None


def _audio_model_for(purpose: str, config: AgentModelConfig) -> LLMModel:
    model = config.stt_model if purpose == ModelCategory.STT else config.tts_model
    if model is None or not model.is_active or not model.provider.is_active:
        raise ModelNotConfigured(
            f"Nenhum modelo ativo configurado para o papel '{purpose}'."
        )
    return _require_key(model)


def get_audio_client(purpose: str) -> AudioClient:
    """Monta o cliente de áudio (STT ou TTS) a partir do `AgentModelConfig` cadastrado.

    O cliente é o SDK da OpenAI, apontado para o mesmo `base_url` compatível com a OpenAI
    que o chat usa: assim um único `LLMProvider` (uma URL, uma chave) atende chat, STT e
    TTS. SDKs próprios de provedor montam o caminho da API por conta própria e esperam
    outra URL base, o que obrigaria a cadastrar o mesmo provedor duas vezes. Tem os mesmos
    limites de tempo e de retentativas do chat, pelo mesmo motivo.
    """
    config = AgentModelConfig.get_solo()
    model = _audio_model_for(purpose, config)
    provider = model.provider
    client = OpenAI(
        api_key=provider.api_key,
        base_url=provider.base_url,
        timeout=PROVIDER_TIMEOUT_SECONDS,
        max_retries=PROVIDER_MAX_RETRIES,
    )
    return AudioClient(client=client, model_id=model.model_id, model=model)


def log_active_models() -> None:
    """Imprime, uma vez por sessão, qual modelo/provedor atende cada papel configurado."""
    config = AgentModelConfig.get_solo()
    roles = (
        ("persona", config.persona_model),
        ("judge", config.judge_model),
        ("stt", config.stt_model),
        ("tts", config.tts_model),
        ("router", config.router_model),
    )
    for label, model in roles:
        if model is None or not model.is_active or not model.provider.is_active:
            print(f"[llm] {label}: nao configurado")
        else:
            print(f"[llm] {label}: provider={model.provider.code} model={model.model_id}")


def get_structured_llm(purpose: str, schema: type) -> _StructuredAgent:
    """Monta o cliente do papel pedido, já amarrado a um schema de saída estruturada.

    O método é o que o modelo do papel declara em `structured_output_method`, sempre via
    `create_agent`:

    - `ToolStrategy` (padrão): força a chamada da ferramenta. Foi o único caminho
      confiável no Ollama Cloud, onde `ProviderStrategy` falhou em todas as tentativas e
      `with_structured_output` já devolveu texto solto, `None` ou objeto incompleto. Na
      Groq, porém, o modelo às vezes responde em texto em vez de chamar a ferramenta, e o
      provedor recusa com HTTP 400.
    - `ProviderStrategy` estrito: o provedor restringe a geração ao schema. Na Groq, com
      os gpt-oss, foi o método sem recusa nem fala vazia em 22 de 22 chamadas.
    """
    config = AgentModelConfig.get_solo()
    model = _model_for(purpose, config)
    llm = get_llm(purpose)
    if model.structured_output_method == StructuredOutputMethod.JSON_SCHEMA_STRICT:
        response_format = ProviderStrategy(schema, strict=True)
    else:
        response_format = ToolStrategy(schema)
    agent = create_agent(model=llm, tools=[], response_format=response_format)
    return _StructuredAgent(agent, schema, purpose, model)
