from django.apps import AppConfig


class AgentsConfig(AppConfig):
    """Núcleo conversacional: grafo de execução de um cenário e seus serviços de apoio."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.agents"
    label = "agents"
