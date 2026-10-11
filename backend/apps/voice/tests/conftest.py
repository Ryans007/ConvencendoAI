import pytest

from apps.voice import consumers as voice_consumers


@pytest.fixture(autouse=True)
def open_journey(request, monkeypatch):
    """Libera a jornada nos testes do consumidor, que abrem qualquer cenário com um aluno novo.

    A regra de acesso à sessão tem os próprios testes, em `test_journey_access`, que rodam com
    a regra de verdade; os demais testam outra coisa e não devem depender da progressão.
    """
    if request.module.__name__.endswith("test_journey_access"):
        return
    monkeypatch.setattr(voice_consumers, "session_access_denial", lambda user, scenario, level: None)
