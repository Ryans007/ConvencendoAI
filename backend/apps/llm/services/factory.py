from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from apps.llm.constants import ModelPurpose
from apps.llm.models import AgentModelConfig, LLMModel

_TEMPERATURE_BY_PURPOSE = {
    ModelPurpose.PERSONA: 0.7,
    ModelPurpose.JUDGE: 0.0,
}


class ModelNotConfigured(RuntimeError):
    """Nenhum modelo ativo está configurado para o papel pedido."""


def _model_for(purpose: str, config: AgentModelConfig) -> LLMModel:
    model = (
        config.persona_model if purpose == ModelPurpose.PERSONA else config.judge_model
    )
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
