from collections import defaultdict

from django import forms
from django.contrib import admin

from apps.catalog.constants import RolePresence
from apps.catalog.models import (
    Criterion,
    Scenario,
    ScenarioLevelHint,
    ScenarioLevelWeightOverride,
    ScenarioRole,
)
from apps.catalog.validators import (
    CastEntry,
    clean_scenario_cast,
    clean_scenario_level_weights,
)


class CriterionInline(admin.TabularInline):
    """Critérios de aceite do cenário, ocultos do aluno até o relatório final."""

    model = Criterion
    extra = 1
    fields = ["code", "text", "order", "levels"]


class ScenarioRoleFormSet(forms.BaseInlineFormSet):
    """Valida o elenco inteiro do cenário: tamanho, presença e quem decide ou abre a cena."""

    def clean(self) -> None:
        super().clean()
        cast = [
            CastEntry(
                presence=form.cleaned_data.get("presence") or RolePresence.PRINCIPAL,
                decides_outcome=bool(form.cleaned_data.get("decides_outcome")),
                opening_order=form.cleaned_data.get("opening_order") or 0,
            )
            for form in self.forms
            if hasattr(form, "cleaned_data")
            and form.cleaned_data
            and not form.cleaned_data.get("DELETE")
        ]
        clean_scenario_cast(cast)


class ScenarioRoleInline(admin.TabularInline):
    """O papel de cada persona escalada neste cenário."""

    model = ScenarioRole
    formset = ScenarioRoleFormSet
    extra = 1
    autocomplete_fields = ["persona", "archetype"]
    fields = [
        "persona",
        "archetype",
        "scene_function",
        "traits",
        "resistance",
        "concession",
        "extra_instruction",
        "decides_outcome",
        "presence",
        "entry_cue",
        "opening_order",
        "scaffolding_levels",
    ]


class ScenarioLevelHintInline(admin.TabularInline):
    """Pista final sobrescrita para um nível específico deste cenário."""

    model = ScenarioLevelHint
    extra = 0
    fields = ["level", "closing_hint_override"]


class ScenarioLevelWeightOverrideFormSet(forms.BaseInlineFormSet):
    """Valida, por nível, que os pesos efetivos do cenário somam 100.

    As linhas deste formset podem cobrir mais de um nível ao mesmo tempo — os
    ajustes de níveis diferentes são independentes, então a soma é verificada
    dentro de cada grupo de mesmo nível, não sobre o formset inteiro.
    """

    def clean(self) -> None:
        super().clean()
        overrides_by_level: dict = defaultdict(dict)
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            level = form.cleaned_data.get("level")
            dimension = form.cleaned_data.get("dimension")
            weight = form.cleaned_data.get("weight")
            if level and dimension and weight is not None:
                overrides_by_level[level][dimension] = weight

        for level, overrides in overrides_by_level.items():
            clean_scenario_level_weights(level, overrides)


class ScenarioLevelWeightOverrideInline(admin.TabularInline):
    """Pesos de rúbrica sobrescritos para um nível específico deste cenário."""

    model = ScenarioLevelWeightOverride
    formset = ScenarioLevelWeightOverrideFormSet
    extra = 0
    fields = ["level", "dimension", "weight"]


@admin.register(Scenario)
class ScenarioAdmin(admin.ModelAdmin):
    """Um cenário completo — critérios, papéis de persona e ajustes por nível —
    cadastrável numa única tela.
    """

    list_display = [
        "title",
        "track",
        "order",
        "cooldown_hours",
        "max_consecutive_turns",
        "max_turns",
    ]
    list_filter = ["track"]
    search_fields = ["title", "slug"]
    autocomplete_fields = ["track"]
    inlines = [
        CriterionInline,
        ScenarioRoleInline,
        ScenarioLevelHintInline,
        ScenarioLevelWeightOverrideInline,
    ]
