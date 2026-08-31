import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = pytest.mark.django_db


def test_run_scenario_rejects_unknown_user():
    with pytest.raises(CommandError, match="Usuário"):
        call_command("run_scenario", user="ninguem", scenario="negociar-prazo", level=3)


def test_run_scenario_rejects_unknown_scenario(django_user_model):
    django_user_model.objects.create(username="aluno")
    with pytest.raises(CommandError, match="Cenário"):
        call_command("run_scenario", user="aluno", scenario="nao-existe", level=3)


def test_run_scenario_rejects_unknown_level(django_user_model):
    django_user_model.objects.create(username="aluno")
    with pytest.raises(CommandError, match="Nível"):
        call_command("run_scenario", user="aluno", scenario="negociar-prazo", level=9)
