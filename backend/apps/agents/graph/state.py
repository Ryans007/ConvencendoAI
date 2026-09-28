from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ScenarioState(TypedDict):
    """Estado que trafega entre os nós do grafo durante a execução de um cenário.

    Os critérios de aceite não fazem parte deste estado: quem os valida é o
    avaliador, ao fim da execução, lendo a transcrição inteira.

    `taking_over` fica ligado só na rodada em que o equilíbrio de turno entregou a vez a
    outra persona: é ela quem conduz a transição, reagindo à resposta que o aluno deu ao
    outro personagem.
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]
    current_speaker: str
    turn_count: int
    scene_resolved: bool
    should_end: bool
    taking_over: bool
