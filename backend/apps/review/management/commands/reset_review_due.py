from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.review.services.reset_due import make_items_due


class Command(BaseCommand):
    """Deixa os itens de revisão de um aluno vencidos hoje, para testar a rodada."""

    help = "Faz todos os itens de revisão ativos de um aluno vencerem hoje (uso em testes)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--user", required=True, help="username do aluno")
        parser.add_argument(
            "--restart-boxes",
            action="store_true",
            help="também volta os itens para a primeira caixa (1 dia)",
        )

    def handle(self, *args, **options) -> None:
        user_model = get_user_model()
        try:
            user = user_model.objects.get(username=options["user"])
        except user_model.DoesNotExist as exc:
            raise CommandError(f"Usuário '{options['user']}' não existe.") from exc

        changed = make_items_due(
            user, timezone.localdate(), restart_boxes=options["restart_boxes"]
        )
        self.stdout.write(
            self.style.SUCCESS(f"{changed} item(ns) de revisão de '{user}' vencem hoje.")
        )
