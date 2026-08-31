from django.apps import AppConfig


class LlmConfig(AppConfig):
    """Cadastro de provedor e modelo de LLM, e configuração de qual atende cada papel."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.llm"
    label = "llm"
