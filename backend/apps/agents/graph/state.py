from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ScenarioState(TypedDict):
    """Estado que trafega entre os nós do grafo durante a execução de um cenário.

    Os critérios de aceite não fazem parte deste estado: quem os valida é o
    avaliador, ao fim da execução, lendo a transcrição inteira.
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]
    current_speaker: str
    turn_count: int
    scene_resolved: bool
    should_end: bool
