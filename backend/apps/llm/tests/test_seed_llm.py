from io import StringIO

import pytest
from django.core.management import call_command

from apps.llm.models import LLMProvider

pytestmark = pytest.mark.django_db

_SECRET = "gsk_SEGREDO123"


def _seed() -> str:
    out = StringIO()
    call_command("seed_llm", stdout=out)
    return out.getvalue()


def test_the_output_lists_what_was_created(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", _SECRET)

    output = _seed()

    assert "provedor groq: criado" in output
    assert "chave: gravada a partir de GROQ_API_KEY" in output
    assert "modelo openai/gpt-oss-20b: criado" in output
    assert "papel persona_model: preenchido" in output
    assert "Pronto para uso." in output
    assert LLMProvider.objects.get(code="groq").api_key == _SECRET


def test_the_second_run_says_everything_already_existed(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", _SECRET)
    _seed()

    output = _seed()

    assert "criado" not in output and "preenchido\n" not in output
    assert "chave: já cadastrada, mantida" in output
    assert "nada mudou" in output


@pytest.mark.parametrize("value", [None, "", "   "])
def test_without_the_variable_it_warns_that_the_key_is_missing(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
    else:
        monkeypatch.setenv("GROQ_API_KEY", value)

    output = _seed()

    assert "sem chave" in output and "GROQ_API_KEY" in output
    assert "Pronto para uso." not in output
    assert not LLMProvider.objects.get(code="groq").has_api_key


def test_the_output_never_contains_the_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", _SECRET)

    outputs = _seed() + _seed()

    assert _SECRET not in outputs
    assert "SEGREDO" not in outputs
