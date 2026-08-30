from django.contrib import admin

from apps.catalog.models import Scenario, Track


class ScenarioInline(admin.TabularInline):
    """Resumo dos cenários da trilha, com atalho para a edição completa de cada um."""

    model = Scenario
    extra = 0
    fields = ["title", "order"]
    show_change_link = True


@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    """Trilhas, com a lista ordenada de seus cenários."""

    list_display = ["title", "order"]
    search_fields = ["title", "slug"]
    inlines = [ScenarioInline]
