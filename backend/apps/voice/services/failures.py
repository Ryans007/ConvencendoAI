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
    UNEXPECTED = "unexpected"


FAILURE_DESCRIPTIONS: dict[SessionErrorCode, str] = {
    SessionErrorCode.PROVIDER_RATE_LIMITED: "O provedor de IA atingiu o limite de uso.",
    SessionErrorCode.PROVIDER_UNAVAILABLE: "O provedor de IA está indisponível.",
    SessionErrorCode.REPORT_FAILED: "A sessão terminou, mas a avaliação falhou.",
    SessionErrorCode.UNEXPECTED: "Erro inesperado durante a sessão.",
}


INVALID_MEDIA_CODE = "invalid_media_file"


def is_invalid_audio(exc: BaseException) -> bool:
    """O provedor de STT recusou o áudio por ele não ser um arquivo de mídia válido.

    É um problema da gravação, e não do provedor: um toque curto demais no botão de falar
    gera um arquivo de poucos bytes, sem áudio de verdade. Tratar como queda do provedor
    encerraria a sessão do aluno por causa de um toque, então quem chama deve pedir que ele
    fale de novo, como faz com uma transcrição vazia.
    """
    return isinstance(exc, openai.BadRequestError) and exc.code == INVALID_MEDIA_CODE


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
