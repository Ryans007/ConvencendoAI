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

    `addressed_by_student` fica ligado só na rodada em que o roteador reconheceu que o
    aluno falou com uma persona específica, inclusive a que já era a da vez: quem foi
    chamado responde ao que ele disse e fecha a rodada.

    `redirect_to` fica preenchido só na rodada em que o aluno chamou uma persona para um
    assunto que é de outro personagem: é a chave de quem recebe a passagem de vez, feita pelo
    sistema e não pela persona.
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]
    current_speaker: str
    turn_count: int
    scene_resolved: bool
    should_end: bool
    taking_over: bool
    addressed_by_student: bool
    redirect_to: str
