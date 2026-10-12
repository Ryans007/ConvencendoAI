import pytest
from django.test import override_settings

from apps.llm.services.conversation_log import conversation_log

SPOKEN = "my passport number is 123456"


def test_content_is_logged_when_enabled(capsys: pytest.CaptureFixture[str]) -> None:
    """Com o log de conversa ligado, o texto sai como sempre saiu."""
    with override_settings(LOG_CONVERSATION_CONTENT=True):
        conversation_log("You", SPOKEN)

    assert capsys.readouterr().out == f"You: {SPOKEN}\n"


def test_only_the_length_is_logged_when_disabled(capsys: pytest.CaptureFixture[str]) -> None:
    """Desligado, a linha de diagnóstico continua, mas sem o texto."""
    with override_settings(LOG_CONVERSATION_CONTENT=False):
        conversation_log("You", SPOKEN)

    output = capsys.readouterr().out
    assert SPOKEN not in output
    assert output == f"You: ({len(SPOKEN)} caracteres)\n"
