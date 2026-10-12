from enum import StrEnum

import openai

from apps.llm.services.factory import ModelNotConfigured


class SessionErrorCode(StrEnum):
    """Código estável do aviso de erro que o servidor da sessão manda ao cliente.

    O cliente escolhe a mensagem do aluno a partir do código, então estes valores são um
    contrato com a tela: mudar um deles exige mudar a tela junto.
    """

    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    REPORT_FAILED = "report_failed"
    SESSION_ALREADY_OPEN = "session_already_open"
    DAILY_SESSION_LIMIT = "daily_session_limit"
    SCENARIO_LOCKED = "scenario_locked"
    LEVEL_IN_COOLDOWN = "level_in_cooldown"
    UNEXPECTED = "unexpected"


FAILURE_DESCRIPTIONS: dict[SessionErrorCode, str] = {
    SessionErrorCode.PROVIDER_RATE_LIMITED: "O provedor de IA atingiu o limite de uso.",
    SessionErrorCode.PROVIDER_UNAVAILABLE: "O provedor de IA está indisponível.",
    SessionErrorCode.REPORT_FAILED: "A sessão terminou, mas a avaliação falhou.",
    SessionErrorCode.SESSION_ALREADY_OPEN: "O aluno já tem uma sessão de voz aberta.",
    SessionErrorCode.DAILY_SESSION_LIMIT: "O aluno atingiu o limite de sessões de voz de hoje.",
    SessionErrorCode.SCENARIO_LOCKED: "O cenário ainda não está liberado para o aluno.",
    SessionErrorCode.LEVEL_IN_COOLDOWN: "O nível ainda está no intervalo entre tentativas.",
    SessionErrorCode.UNEXPECTED: "Erro inesperado durante a sessão.",
}


def classify_failure(exc: BaseException) -> SessionErrorCode:
    """Traduz a exceção de uma etapa da sessão no código que o cliente recebe.

    O limite de uso do provedor (HTTP 429) é separado dos demais erros porque o aluno
    precisa esperar, e o resto dos erros do provedor — conexão, tempo esgotado, outras
    respostas de erro e modelo não configurado — são, para ele, o serviço fora do ar.
    Qualquer outra exceção é inesperada. `REPORT_FAILED` não sai daqui: é o código da fase
    de avaliação, usado quando ela falha por qualquer motivo.
    """
    if isinstance(exc, openai.RateLimitError):
        return SessionErrorCode.PROVIDER_RATE_LIMITED
    if isinstance(exc, (openai.APIConnectionError, openai.APIStatusError, ModelNotConfigured)):
        return SessionErrorCode.PROVIDER_UNAVAILABLE
    return SessionErrorCode.UNEXPECTED
