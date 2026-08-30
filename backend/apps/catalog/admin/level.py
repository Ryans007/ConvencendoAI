from django import forms
from django.contrib import admin

from apps.catalog.models import Level, LevelDefaultWeight
from apps.catalog.validators import clean_level_weights


class LevelDefaultWeightFormSet(forms.BaseInlineFormSet):
    """Valida, sobre o conjunto inteiro de linhas, que os pesos padrão do nível
    somam 100 — uma linha isolada não tem como saber se soma certo sozinha.
    """

    def clean(self) -> None:
        super().clean()
        weights: dict[str, int] = {}
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            dimension = form.cleaned_data.get("dimension")
            weight = form.cleaned_data.get("weight")
            if dimension and weight is not None:
                weights[dimension] = weight
        clean_level_weights(self.instance, weights)


class LevelDefaultWeightInline(admin.TabularInline):
    """Peso padrão de cada dimensão da rúbrica para este nível."""

    model = LevelDefaultWeight
    formset = LevelDefaultWeightFormSet
    extra = 0
    fields = ["dimension", "weight"]


@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    """Os três níveis de dificuldade, com seus pesos padrão aninhados."""

    list_display = ["order", "name", "expected_cefr", "max_turns"]
    inlines = [LevelDefaultWeightInline]
