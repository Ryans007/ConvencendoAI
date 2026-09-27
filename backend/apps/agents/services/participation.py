import re
from dataclasses import dataclass

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from apps.agents.services.scenario_content import ScenarioContent

_SPEAKER_PREFIX = re.compile(r"^\[([^\]]+)\]")


@dataclass(frozen=True)
class SceneParticipation:
    """Quanto cada personagem já participou da cena, do ponto de vista de quem vai falar.

    `lines_by_role` conta as falas de cada chave de papel. `consecutive_rounds_led` conta
    as rodadas seguidas, até a mais recente, em que a persona da vez foi a última a falar
    antes do aluno — numa rodada com passagem de vez, quem conduz é quem falou por último.
    """

    lines_by_role: dict[str, int]
    consecutive_rounds_led: int


def _speaker_key(message: AIMessage, key_by_name: dict[str, str]) -> str | None:
    match = _SPEAKER_PREFIX.match(message.content or "")
    if not match:
        return None
    return key_by_name.get(match.group(1))


def scene_participation(
    content: ScenarioContent, speaker_key: str, history: list[BaseMessage]
) -> SceneParticipation:
    """Calcula, pelo histórico da execução, a participação de cada personagem na cena.

    Calculado pelo código e entregue à persona como fato, em vez de pedir que o modelo
    conte sozinho: medido em teste real, o modelo não percebe quando está monopolizando
    a conversa.
    """
    key_by_name = {role.name: role.key for role in content.roles}
    lines_by_role = {key: 0 for key in content.role_keys()}

    round_leaders: list[str | None] = []
    current_leader: str | None = None
    for message in history:
        if isinstance(message, HumanMessage):
            round_leaders.append(current_leader)
            current_leader = None
        elif isinstance(message, AIMessage):
            key = _speaker_key(message, key_by_name)
            if key is not None:
                lines_by_role[key] += 1
                current_leader = key
    if current_leader is not None:
        round_leaders.append(current_leader)

    consecutive = 0
    for leader in reversed(round_leaders):
        if leader is None:
            continue
        if leader != speaker_key:
            break
        consecutive += 1

    return SceneParticipation(lines_by_role=lines_by_role, consecutive_rounds_led=consecutive)
