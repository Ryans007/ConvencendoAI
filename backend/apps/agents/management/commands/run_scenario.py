from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.agents.services.session_runner import run_and_record_attempt
from apps.catalog.models import Level, Scenario
from apps.llm.services.factory import log_active_models


class Command(BaseCommand):
    """Executa um cenário do catálogo do início ao fim, por texto, e persiste a tentativa."""

    help = "Roda um cenário do catálogo em modo texto e grava o resultado como uma tentativa."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--user", required=True, help="username do aluno")
        parser.add_argument("--scenario", required=True, help="slug do cenário")
        parser.add_argument(
            "--level", required=True, type=int, help="ordem do nível (1, 2 ou 3)"
        )

    def handle(self, *args, **options) -> None:
        user_model = get_user_model()
        try:
            user = user_model.objects.get(username=options["user"])
        except user_model.DoesNotExist as exc:
            raise CommandError(f"Usuário '{options['user']}' não existe.") from exc

        try:
            scenario = Scenario.objects.get(slug=options["scenario"])
        except Scenario.DoesNotExist as exc:
            raise CommandError(f"Cenário '{options['scenario']}' não existe.") from exc

        try:
            level = Level.objects.get(order=options["level"])
        except Level.DoesNotExist as exc:
            raise CommandError(f"Nível de ordem {options['level']} não existe.") from exc

        self.stdout.write(f"\n{scenario.title} — nível {level.name}\n")
        self.stdout.write(f"Objective: {scenario.objective}\n")
        self.stdout.write("Send EOF (Ctrl+D, or Ctrl+Z then Enter on Windows) to end early.\n")

        log_active_models()

        attempt = run_and_record_attempt(user, scenario, level)

        status = "passed" if attempt.passed else "not passed"
        self.stdout.write(
            self.style.SUCCESS(
                f"\nAttempt #{attempt.pk} recorded — score {attempt.final_score}/100 ({status})"
            )
        )
