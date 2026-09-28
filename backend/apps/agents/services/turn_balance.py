import random
import re

from langchain_core.messages import AIMessage, BaseMessage

from apps.agents.services.scenario_content import ScenarioContent

MIN_ROUNDS_BEFORE_HANDOVER = 2

_SPEAKER_PREFIX = re.compile(r"^\[([^\]]+)\]")


def should_hand_over(
    consecutive_rounds_led: int, max_consecutive_turns: int, rng: random.Random
) -> bool:
    """A persona da vez deve passar a rodada a outro personagem?

    Sorteia um limite entre `MIN_ROUNDS_BEFORE_HANDOVER` e o máximo do cenário, e a troca
    acontece quando a persona já conduziu pelo menos esse número de rodadas seguidas.
    Sortear a cada rodada, em vez de uma vez por sequência, dispensa guardar o limite no
    estado do grafo: a contagem de rodadas já vem do histórico. O mínimo 2 evita a troca
    logo depois de uma única rodada; ao atingir o máximo, qualquer sorteio dispara a troca.
    """
    upper = max(1, max_consecutive_turns)
    lower = min(MIN_ROUNDS_BEFORE_HANDOVER, upper)
    return consecutive_rounds_led >= rng.randint(lower, upper)


def next_leader(content: ScenarioContent, current_key: str, history: list[BaseMessage]) -> str:
    """Escolhe quem conduz a rodada quando a persona da vez passa a vez pelo equilíbrio.

    Entre os outros personagens, entra quem falou há mais tempo — quem ainda não falou
    vem primeiro. Com dois personagens, é sempre o outro.
    """
    key_by_name = {role.name: role.key for role in content.roles}
    last_spoke = {key: -1 for key in content.role_keys()}
    for index, message in enumerate(history):
        if not isinstance(message, AIMessage):
            continue
        match = _SPEAKER_PREFIX.match(message.content or "")
        if match and match.group(1) in key_by_name:
            last_spoke[key_by_name[match.group(1)]] = index
    candidates = [key for key in content.role_keys() if key != current_key]
    return min(candidates, key=lambda key: last_spoke[key])
