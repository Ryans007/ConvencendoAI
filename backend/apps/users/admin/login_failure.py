from django.contrib import admin
from django.http import HttpRequest

from apps.users.models import LoginFailure


@admin.register(LoginFailure)
class LoginFailureAdmin(admin.ModelAdmin):
    """Auditoria das senhas erradas: consulta para o superuser, sem edição.

    Mostra o usuário como foi digitado, o IP e o momento de cada tentativa, nunca a senha,
    para o superuser enxergar um ataque em andamento e quem o está fazendo.
    """

    list_display = ["created_at", "username", "ip_address"]
    list_filter = ["created_at"]
    search_fields = ["username", "ip_address"]
    date_hierarchy = "created_at"

    def has_module_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser

    def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
        return request.user.is_superuser

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False
