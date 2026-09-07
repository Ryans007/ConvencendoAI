from django.db import models

from apps.llm.models.llm_model import LLMModel


class AgentModelConfig(models.Model):
    """Configuração única de qual modelo atende cada papel do núcleo conversacional.

    Linha única no sistema inteiro: `save()` força a chave primária, e `get_solo()` é
    o único ponto de leitura esperado pelo resto do código. Existe porque personas e
    avaliador podem usar modelos diferentes; não é configuração por trilha nem por
    aluno.
    """

    persona_model = models.ForeignKey(
        LLMModel, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    judge_model = models.ForeignKey(
        LLMModel, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    stt_model = models.ForeignKey(
        LLMModel, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    tts_model = models.ForeignKey(
        LLMModel, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )

    def save(self, *args, **kwargs) -> None:
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs) -> None:
        raise RuntimeError("AgentModelConfig é singleton: não pode ser removido.")

    @classmethod
    def get_solo(cls) -> "AgentModelConfig":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self) -> str:
        return "Configuração de modelos do núcleo"
