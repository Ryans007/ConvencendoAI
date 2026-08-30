from django.apps import AppConfig


class ProgressConfig(AppConfig):
    """Histórico gerado pelo uso: tentativas, sub-notas e critérios avaliados."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.progress"
    label = "progress"
