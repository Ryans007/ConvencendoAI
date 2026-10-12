from django.conf import settings


def conversation_log(label: str, text: str) -> None:
    """Escreve no log um texto que veio da conversa do aluno ou dos modelos.

    Com `LOG_CONVERSATION_CONTENT` ligado (desenvolvimento), escreve o texto. Desligado
    (padrão, produção), escreve só o tamanho: a linha de diagnóstico continua existindo,
    mas a fala do aluno nunca chega ao log do servidor, que aparece no painel de hospedagem.
    """
    if settings.LOG_CONVERSATION_CONTENT:
        print(f"{label}: {text}")
    else:
        print(f"{label}: ({len(text)} caracteres)")
