import os

from django.core.management.base import BaseCommand

from apps.llm.services.default_setup import PROVIDER_CODE, apply_default_setup

KEY_VARIABLE = "GROQ_API_KEY"


class Command(BaseCommand):
    """Deixa a Groq configurada a partir da `GROQ_API_KEY`, completando só o que falta."""

    help = (
        "Cria o provedor Groq, os modelos gpt-oss-20b, gpt-oss-120b, whisper e orpheus, e "
        "preenche os papéis vazios. Não altera nada que já existe; seguro para rodar sempre."
    )

    def handle(self, *args, **options) -> None:
        report = apply_default_setup(os.environ.get(KEY_VARIABLE, ""))

        def line(created: bool, text: str) -> None:
            mark = "criado" if created else "já existia"
            self.stdout.write(f"  {text}: {mark}")

        self.stdout.write("Configuração padrão de LLM (Groq):")
        line(report.provider_created, f"provedor {PROVIDER_CODE}")
        if report.key_stored:
            self.stdout.write(f"  chave: gravada a partir de {KEY_VARIABLE}")
        elif report.has_key:
            self.stdout.write("  chave: já cadastrada, mantida")
        for model_id in report.models_created:
            line(True, f"modelo {model_id}")
        for model_id in report.models_existing:
            line(False, f"modelo {model_id}")
        for role in report.roles_filled:
            self.stdout.write(f"  papel {role}: preenchido")
        for role in report.roles_kept:
            self.stdout.write(f"  papel {role}: já preenchido, mantido")

        if not report.has_key:
            self.stdout.write(
                self.style.WARNING(
                    f"Provedor {PROVIDER_CODE} sem chave: defina {KEY_VARIABLE} e rode de novo, "
                    "ou cadastre a chave no admin."
                )
            )
        elif report.changed_anything:
            self.stdout.write(self.style.SUCCESS("Pronto para uso."))
        else:
            self.stdout.write(self.style.SUCCESS("Tudo já estava configurado; nada mudou."))
