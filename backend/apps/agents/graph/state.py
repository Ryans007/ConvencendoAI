from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ScenarioState(TypedDict):
    """Estado que trafega entre os nós do grafo durante a execução de um cenário.

    Os critérios de aceite não fazem parte deste estado: quem os valida é o
    avaliador, ao fim da execução, lendo a transcrição inteira.

    `hand_floor_to` fica preenchido só na rodada em que o equilíbrio de turno ou o assunto
    trocou quem conduz sem o aluno chamar ninguém: é a chave de quem entra. A persona da vez
    reage à resposta do aluno e passa a palavra a ela, e ela fala em seguida, na mesma rodada,
    e faz a pergunta.

    `addressed_by_student` fica ligado só na rodada em que o roteador reconheceu que o
    aluno falou com uma persona específica, inclusive a que já era a da vez: quem foi
    chamado responde ao que ele disse e fecha a rodada.

    `scene_resolved` só é ligado pelo código: no fechamento do limite de turnos. Nenhuma persona
    decide o fim da cena, que termina também a pedido do aluno, tratado fora do grafo.

    `redirect_to` fica preenchido só na rodada em que o aluno chamou uma persona para um
    assunto que é de outro personagem: é a chave de quem recebe a passagem de vez, feita pelo
    sistema e não pela persona.
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]
    current_speaker: str
    turn_count: int
    scene_resolved: bool
    should_end: bool
    hand_floor_to: str
    addressed_by_student: bool
    redirect_to: str
