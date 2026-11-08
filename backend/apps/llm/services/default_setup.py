from dataclasses import dataclass, field

from django.db import transaction

from apps.llm.constants import ModelCategory, StructuredOutputMethod
from apps.llm.models import AgentModelConfig, LLMModel, LLMProvider

PROVIDER_CODE = "groq"
PROVIDER_NAME = "Groq"
PROVIDER_BASE_URL = "https://api.groq.com/openai/v1"

PERSONA_MODEL = "openai/gpt-oss-20b"
REASONING_MODEL = "openai/gpt-oss-120b"
STT_MODEL = "whisper-large-v3-turbo"
TTS_MODEL = "canopylabs/orpheus-v1-english"

_STRICT = StructuredOutputMethod.JSON_SCHEMA_STRICT
_TOOL = StructuredOutputMethod.TOOL_CALLING
_MODELS = (
    (PERSONA_MODEL, "GPT-OSS 20B", ModelCategory.CHAT, _STRICT),
    (REASONING_MODEL, "GPT-OSS 120B", ModelCategory.CHAT, _STRICT),
    (STT_MODEL, "Whisper Large v3 Turbo", ModelCategory.STT, _TOOL),
    (TTS_MODEL, "Orpheus English", ModelCategory.TTS, _TOOL),
)

_ROLES = (
    ("persona_model", PERSONA_MODEL),
    ("judge_model", REASONING_MODEL),
    ("router_model", REASONING_MODEL),
    ("stt_model", STT_MODEL),
    ("tts_model", TTS_MODEL),
)


@dataclass
class SetupReport:
    """O que o seed criou e o que já existia. Nunca guarda o valor da chave."""

    provider_created: bool = False
    key_stored: bool = False
    has_key: bool = False
    models_created: list[str] = field(default_factory=list)
    models_existing: list[str] = field(default_factory=list)
    roles_filled: list[str] = field(default_factory=list)
    roles_kept: list[str] = field(default_factory=list)

    @property
    def changed_anything(self) -> bool:
        return bool(
            self.provider_created or self.key_stored or self.models_created or self.roles_filled
        )


@transaction.atomic
def apply_default_setup(api_key: str) -> SetupReport:
    """Deixa a Groq configurada, completando só o que falta.

    Cria o provedor, os quatro modelos e preenche os papéis vazios. Nada que já existe é
    alterado: uma chave cadastrada no admin, um modelo existente (mesmo desativado) e um papel
    já preenchido ficam como estão. A chave recebida só é gravada se o provedor não tiver uma
    legível. Roda numa transação, para que uma falha no meio não deixe metade configurada.

    Os gpt-oss da Groq usam JSON schema estrito, porque foi o método de saída estruturada que
    não produziu recusa nem fala vazia.
    """
    report = SetupReport()

    provider, report.provider_created = LLMProvider.objects.get_or_create(
        code=PROVIDER_CODE, defaults={"name": PROVIDER_NAME, "base_url": PROVIDER_BASE_URL}
    )
    api_key = (api_key or "").strip()
    if not provider.has_api_key and api_key:
        provider.api_key = api_key
        provider.save(update_fields=["api_key_encrypted"])
        report.key_stored = True
    report.has_key = provider.has_api_key

    models = {}
    for model_id, display_name, category, method in _MODELS:
        model, created = LLMModel.objects.get_or_create(
            provider=provider,
            model_id=model_id,
            defaults={
                "display_name": display_name,
                "category": category,
                "structured_output_method": method,
            },
        )
        models[model_id] = model
        (report.models_created if created else report.models_existing).append(model_id)

    config = AgentModelConfig.get_solo()
    for role, model_id in _ROLES:
        if getattr(config, f"{role}_id") is None:
            setattr(config, role, models[model_id])
            report.roles_filled.append(role)
        else:
            report.roles_kept.append(role)
    if report.roles_filled:
        config.save()

    return report
