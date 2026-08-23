"""Configuracao do app de usuarios."""

from django.apps import AppConfig


class UsersConfig(AppConfig):
    """Registra o app com label curto, que e o usado nas referencias de model."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
    label = "users"
