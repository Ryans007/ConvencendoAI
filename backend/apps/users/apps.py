from django.apps import AppConfig


class UsersConfig(AppConfig):
    """Registra o app com label curto, que e o usado nas referencias de model."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
    label = "users"

    def ready(self) -> None:
        """Liga os receptores que gravam e zeram as senhas erradas do login."""
        from apps.users import signals  # noqa: F401
