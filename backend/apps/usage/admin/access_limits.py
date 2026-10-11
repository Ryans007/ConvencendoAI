from django.contrib import admin
from django.http import HttpRequest

from apps.usage.models import AccessLimits


@admin.register(AccessLimits)
class AccessLimitsAdmin(admin.ModelAdmin):
    """Tela única dos limites de acesso e de uso, só para o superuser.

    Os números protegem o login contra força bruta e o gasto com os provedores de IA, então só
    o superuser os vê e altera. A linha é única e não pode ser apagada.
    """

    fieldsets = [
        (
            "Login: bloqueio por senha errada",
            {
                "fields": [
                    "login_max_failures_per_user",
                    "login_max_failures_per_ip",
                    "login_window_minutes",
                    "login_lockout_minutes",
                ]
            },
        ),
        (
            "Sessão de voz",
            {
                "fields": [
                    "max_open_voice_sessions",
                    "max_voice_sessions_per_day",
                    "max_turn_audio_kb",
                ]
            },
        ),
        ("Revisão", {"fields": ["max_review_calls_per_minute"]}),
    ]

    def has_module_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser

    def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
        return request.user.is_superuser

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return request.user.is_superuser

    def has_add_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser and not AccessLimits.objects.exists()

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False
