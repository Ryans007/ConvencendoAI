from django.contrib import admin

from apps.catalog.models import Persona


@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    """Elenco persistente, independente de cenário."""

    list_display = ["name", "voice"]
    search_fields = ["name"]
