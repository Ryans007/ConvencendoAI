from dataclasses import dataclass

from apps.catalog.models import Level, Scenario
from apps.progress.services.completion import is_scenario_unlocked
from apps.progress.services.level_status import cooldown_remaining

SCENARIO_LOCKED = "scenario_locked"
LEVEL_IN_COOLDOWN = "level_in_cooldown"


@dataclass(frozen=True)
class AccessDenied:
    """Por que o aluno não pode abrir a sessão agora.

    `code` é o contrato com a tela. `retry_after_seconds` só existe no cooldown: é o tempo
    até o nível voltar a ficar disponível.
    """

    code: str
    retry_after_seconds: int | None = None


def session_access_denial(user, scenario: Scenario, level: Level) -> AccessDenied | None:
    """Decide se o aluno pode abrir a sessão deste cenário e nível, ou por que não pode.

    São as mesmas regras que a jornada mostra à tela, sobre as mesmas funções: o cenário só
    está liberado depois de concluir o anterior (e a trilha anterior), e um nível só volta
    depois do intervalo do cenário contado da última tentativa concluída. Sem isso o servidor
    da sessão abriria qualquer cenário e nível para quem abrisse a URL direto. Cenário bloqueado
    vem antes do cooldown, porque é o que o aluno resolve na jornada. O superuser fica fora das
    regras, para poder testar qualquer cenário sem refazer a progressão.
    """
    if user.is_superuser:
        return None
    if not is_scenario_unlocked(user, scenario):
        return AccessDenied(SCENARIO_LOCKED)
    remaining = cooldown_remaining(user, scenario, level)
    if remaining is not None:
        return AccessDenied(LEVEL_IN_COOLDOWN, int(remaining.total_seconds()) + 1)
    return None
