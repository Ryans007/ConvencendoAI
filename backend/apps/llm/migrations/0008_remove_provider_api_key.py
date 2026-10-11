import os

from django.db import migrations, models


class MissingEnvironmentKeys(RuntimeError):
    """Algum provedor com chave no banco ainda não tem a variável de ambiente definida."""


def require_keys_in_the_environment(apps, schema_editor):
    """Para antes de apagar uma chave que o ambiente ainda não tem.

    Remover o campo destruiria a única cópia da chave se ela não estivesse no ambiente. Por isso,
    para cada provedor que tem chave gravada, a variável precisa estar definida e não vazia. Se
    faltar alguma, a migration para sem apagar nada, e a mensagem lista só os NOMES das variáveis,
    nunca um valor. O valor do ambiente não é comparado com o do banco: quem define a variável
    decide a chave, inclusive uma já rotacionada.
    """
    LLMProvider = apps.get_model("llm", "LLMProvider")
    missing = [
        provider.api_key_env
        for provider in LLMProvider.objects.exclude(api_key="")
        if not os.environ.get(provider.api_key_env, "").strip()
    ]
    if missing:
        raise MissingEnvironmentKeys(
            "Antes de remover as chaves do banco, defina no ambiente (por exemplo no .env) as "
            f"variáveis: {', '.join(sorted(missing))}. Nada foi apagado."
        )


def restore_keys_from_the_environment(apps, schema_editor):
    """Ao desfazer, devolve ao banco a chave lida do ambiente de cada provedor."""
    LLMProvider = apps.get_model("llm", "LLMProvider")
    for provider in LLMProvider.objects.all():
        provider.api_key = os.environ.get(provider.api_key_env, "").strip()
        provider.save(update_fields=["api_key"])


class Migration(migrations.Migration):

    dependencies = [
        ("llm", "0007_provider_api_key_env"),
    ]

    operations = [
        migrations.AlterField(
            model_name="llmprovider",
            name="api_key",
            field=models.CharField(default="", max_length=200),
        ),
        migrations.RunPython(require_keys_in_the_environment, restore_keys_from_the_environment),
        migrations.RemoveField(model_name="llmprovider", name="api_key"),
    ]
