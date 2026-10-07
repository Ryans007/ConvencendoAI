from django.apps import AppConfig


class ReviewConfig(AppConfig):
    """Repetição espaçada: os erros de linguagem do aluno e quando cada um deve voltar."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.review"
    label = "review"
    verbose_name = "Revisão"
