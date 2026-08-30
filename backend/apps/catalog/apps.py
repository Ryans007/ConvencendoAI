from django.apps import AppConfig


class CatalogConfig(AppConfig):
    """Conteúdo cadastrável: trilhas, cenários, personas, critérios e níveis."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    label = "catalog"
