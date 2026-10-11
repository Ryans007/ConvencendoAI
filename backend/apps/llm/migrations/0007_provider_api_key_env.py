import django.core.validators
from django.db import migrations, models


def name_the_environment_variables(apps, schema_editor):
    """Dá a cada provedor o nome da variável de ambiente da chave: o código, em maiúsculas.

    O `ollama-cloud` vira `OLLAMA_CLOUD_API_KEY`. Só o nome é gravado: a chave atual continua
    no campo antigo até a migration seguinte conferir que o ambiente a tem.
    """
    LLMProvider = apps.get_model("llm", "LLMProvider")
    for provider in LLMProvider.objects.all():
        provider.api_key_env = f"{provider.code.upper().replace('-', '_')}_API_KEY"
        provider.save(update_fields=["api_key_env"])


class Migration(migrations.Migration):

    dependencies = [
        ("llm", "0006_model_prices"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmprovider",
            name="api_key_env",
            field=models.CharField(
                default="",
                help_text=(
                    "O nome da variável de ambiente que guarda a chave de acesso deste provedor, "
                    "como GROQ_API_KEY. A chave em si fica só no ambiente do servidor, nunca aqui."
                ),
                max_length=80,
                validators=[
                    django.core.validators.RegexValidator(
                        "^[A-Z][A-Z0-9_]*$",
                        "Use só letras maiúsculas, números e sublinhado, começando por letra "
                        "(ex.: GROQ_API_KEY).",
                    )
                ],
                verbose_name="variável de ambiente da chave",
            ),
            preserve_default=False,
        ),
        migrations.RunPython(name_the_environment_variables, migrations.RunPython.noop),
    ]
