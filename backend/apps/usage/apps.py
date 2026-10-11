from django.apps import AppConfig


class UsageConfig(AppConfig):
    """Registra o app de uso e estatísticas, com label curto para as referências de model."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.usage"
    label = "usage"
