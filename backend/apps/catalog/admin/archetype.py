from django.contrib import admin

from apps.catalog.models import Archetype


@admin.register(Archetype)
class ArchetypeAdmin(admin.ModelAdmin):
    """Arquétipos interacionais, cadastráveis sem exigir alteração de código."""

    list_display = ["name"]
    search_fields = ["name"]
