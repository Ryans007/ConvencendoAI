import os

from django.db import migrations, models

from apps.llm.key_box import seal


def import_keys_from_environment(apps, schema_editor):
    """Grava no banco, criptografada, a chave que cada provedor tem hoje no ambiente.

    Assim a atualização não derruba um provedor que já funcionava. A falta da variável não
    impede a atualização: o provedor fica sem chave, aparece como "não definida" no admin, e
    basta cadastrá-la lá. A mensagem lista só os códigos dos provedores, nunca um valor.
    """
    LLMProvider = apps.get_model("llm", "LLMProvider")
    without_key = []
    for provider in LLMProvider.objects.all():
        value = os.environ.get(provider.api_key_env, "").strip()
        if not value:
            without_key.append(provider.code)
            continue
        provider.api_key_encrypted = seal(value)
        provider.save(update_fields=["api_key_encrypted"])
    if without_key:
        print(
            "\n  Provedores sem chave no ambiente, cadastre a chave no admin: "
            f"{', '.join(sorted(without_key))}"
        )


def name_environment_variables(apps, schema_editor):
    """Ao desfazer, dá a cada provedor o nome da variável de ambiente, como a migration 0007.

    A chave gravada no banco é descartada: o runtime anterior volta a ler a chave do ambiente.
    """
    LLMProvider = apps.get_model("llm", "LLMProvider")
    for provider in LLMProvider.objects.all():
        provider.api_key_env = f"{provider.code.upper().replace('-', '_')}_API_KEY"
        provider.save(update_fields=["api_key_env"])


class Migration(migrations.Migration):
    """Troca o nome da variável de ambiente pela chave criptografada no banco.

    Antes de remover `api_key_env`, a coluna ganha um default vazio: assim, desfazer o
    `RemoveField` recria a coluna mesmo com provedores cadastrados, e o `RunPython` reverso
    preenche os nomes das variáveis em seguida.
    """

    dependencies = [
        ("llm", "0008_remove_provider_api_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmprovider",
            name="api_key_encrypted",
            field=models.TextField(blank=True, default="", editable=False),
        ),
        migrations.AlterField(
            model_name="llmprovider",
            name="api_key_env",
            field=models.CharField(default="", max_length=80),
        ),
        migrations.RunPython(import_keys_from_environment, name_environment_variables),
        migrations.RemoveField(model_name="llmprovider", name="api_key_env"),
    ]
