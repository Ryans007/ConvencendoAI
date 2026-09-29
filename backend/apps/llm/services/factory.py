import time
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy, ToolStrategy
from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI
from openai import BadRequestError, OpenAI

from apps.llm.constants import ModelCategory, ModelPurpose, StructuredOutputMethod
from apps.llm.models import AgentModelConfig, LLMModel

_TEMPERATURE_BY_PURPOSE = {
    ModelPurpose.PERSONA: 0.7,
    ModelPurpose.JUDGE: 0.0,
    ModelPurpose.ROUTER: 0.0,
}

_FIELD_BY_PURPOSE = {
    ModelPurpose.PERSONA: "persona_model",
    ModelPurpose.JUDGE: "judge_model",
    ModelPurpose.ROUTER: "router_model",
}


class ModelNotConfigured(RuntimeError):
    """Nenhum modelo ativo está configurado para o papel pedido."""


def _model_for(purpose: str, config: AgentModelConfig) -> LLMModel:
    model = getattr(config, _FIELD_BY_PURPOSE[purpose])
    if model is None or not model.is_active or not model.provider.is_active:
        raise ModelNotConfigured(
            f"Nenhum modelo ativo configurado para o papel '{purpose}'."
        )
    return model


def get_llm(purpose: str) -> ChatOpenAI:
    """Monta o cliente do papel pedido a partir do `AgentModelConfig` cadastrado.

    O cliente é sempre `ChatOpenAI`: nenhum provedor exige um SDK próprio, todos
    falam uma API compatível com a da OpenAI.
    """
    config = AgentModelConfig.get_solo()
    model = _model_for(purpose, config)
    provider = model.provider
    return ChatOpenAI(
        model=model.model_id,
        api_key=provider.api_key,
        base_url=provider.base_url,
        temperature=_TEMPERATURE_BY_PURPOSE[purpose],
    )


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
    """

    _ATTEMPTS = 2
    _SCHEMA_REFUSAL_CODES = frozenset(
        {"tool_use_failed", "output_parse_failed", "json_validate_failed"}
    )

    def __init__(self, agent, schema: type, purpose: str):
        self._agent = agent
        self._schema = schema
        self._purpose = purpose

    def _log_missing_response(self, new_messages: list[BaseMessage]) -> None:
        last = next(
            (message for message in reversed(new_messages) if isinstance(message, AIMessage)),
            None,
        )
        if last is None:
            print(f"[warning] {self._purpose}: agente terminou sem nenhuma resposta do modelo")
            return
        tool_calls = [call.get("name") for call in last.tool_calls]
        print(
            f"[warning] {self._purpose}: resposta sem schema preenchido; "
            f"content={str(last.content)[:200]!r} tool_calls={tool_calls}"
        )

    def invoke(self, messages: list[BaseMessage]):
        started_at = time.monotonic()
        model_calls = 0
        structured = None
        for _ in range(self._ATTEMPTS):
            try:
                result = self._agent.invoke({"messages": messages})
            except BadRequestError as exc:
                if exc.code not in self._SCHEMA_REFUSAL_CODES:
                    raise
                model_calls += 1
                body = exc.body if isinstance(exc.body, dict) else {}
                generated = str(body.get("failed_generation", ""))[:200]
                print(
                    f"[warning] {self._purpose}: provedor recusou a resposta fora do schema "
                    f"({exc.code}); gerado={generated!r}"
                )
                continue
            new_messages = result.get("messages", [])[len(messages) :]
            model_calls += sum(1 for message in new_messages if isinstance(message, AIMessage))
            structured = result.get("structured_response")
            if structured is not None:
                break
            self._log_missing_response(new_messages)
        elapsed = time.monotonic() - started_at
        print(f"[timing] {self._purpose}: {elapsed:.2f}s ({model_calls} model call(s))")
        return structured or self._schema()


@dataclass(frozen=True)
class AudioClient:
    """Cliente de áudio já resolvido, com o identificador de modelo que a chamada exige.

    O cliente de áudio, ao contrário do `ChatOpenAI`, não recebe o modelo no construtor —
    cada chamada (`audio.transcriptions.create`, `audio.speech.create`) pede o `model` à
    parte.
    """

    client: OpenAI
    model_id: str


def _audio_model_for(purpose: str, config: AgentModelConfig) -> LLMModel:
    model = config.stt_model if purpose == ModelCategory.STT else config.tts_model
    if model is None or not model.is_active or not model.provider.is_active:
        raise ModelNotConfigured(
            f"Nenhum modelo ativo configurado para o papel '{purpose}'."
        )
    return model


def get_audio_client(purpose: str) -> AudioClient:
    """Monta o cliente de áudio (STT ou TTS) a partir do `AgentModelConfig` cadastrado.

    O cliente é o SDK da OpenAI, apontado para o mesmo `base_url` compatível com a OpenAI
    que o chat usa: assim um único `LLMProvider` (uma URL, uma chave) atende chat, STT e
    TTS. SDKs próprios de provedor montam o caminho da API por conta própria e esperam
    outra URL base, o que obrigaria a cadastrar o mesmo provedor duas vezes.
    """
    config = AgentModelConfig.get_solo()
    model = _audio_model_for(purpose, config)
    provider = model.provider
    client = OpenAI(api_key=provider.api_key, base_url=provider.base_url)
    return AudioClient(client=client, model_id=model.model_id)


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
    return _StructuredAgent(agent, schema, purpose)
