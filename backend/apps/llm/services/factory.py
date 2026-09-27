from dataclasses import dataclass

from groq import Groq
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from apps.llm.constants import ModelCategory, ModelPurpose
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
    resto do código espera, sem expor o estado inteiro do agente (histórico, etc.)."""

    def __init__(self, agent, schema: type):
        self._agent = agent
        self._schema = schema

    def invoke(self, messages: list[BaseMessage]):
        result = self._agent.invoke({"messages": messages})
        return result.get("structured_response") or self._schema()


@dataclass(frozen=True)
class AudioClient:
    """Cliente de áudio já resolvido, com o identificador de modelo que a chamada exige.

    O cliente Groq, ao contrário do `ChatOpenAI`, não recebe o modelo no construtor — cada
    chamada (`audio.transcriptions.create`, `audio.speech.create`) pede o `model` à parte.
    """

    client: Groq
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

    O cliente é sempre `Groq`: mesmo par `base_url`/`api_key` de `LLMProvider`, só o SDK
    muda, porque os endpoints de áudio não são chamadas de chat.
    """
    config = AgentModelConfig.get_solo()
    model = _audio_model_for(purpose, config)
    provider = model.provider
    client = Groq(api_key=provider.api_key, base_url=provider.base_url)
    return AudioClient(client=client, model_id=model.model_id)


def get_structured_llm(purpose: str, schema: type) -> _StructuredAgent:
    """Monta o cliente do papel pedido, já amarrado a um schema de saída estruturada.

    Usa `create_agent` com `ToolStrategy`, que força a chamada da ferramenta — em teste
    real contra este provedor e modelo, é o único caminho confiável: `ProviderStrategy`
    (saída estruturada nativa do provedor) falhou em todas as tentativas, e
    `ChatOpenAI.with_structured_output` nos três métodos (`function_calling`,
    `json_mode`, `json_schema`) já devolveu texto solto, `None`, ou objeto com campo
    obrigatório ausente.
    """
    llm = get_llm(purpose)
    agent = create_agent(model=llm, tools=[], response_format=ToolStrategy(schema))
    return _StructuredAgent(agent, schema)
