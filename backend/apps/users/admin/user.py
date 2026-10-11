from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.utils.cache import add_never_cache_headers

from apps.users.admin.forms import InviteForm
from apps.users.models import User
from apps.users.services.temporary_password import issue_temporary_password

_TEMPORARY_PASSWORD_TEMPLATE = "admin/users/temporary_password.html"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin dos acessos: só o superuser cria um acesso e gera senhas temporárias.

    A criação pede o nome de usuário e o e-mail, e a senha temporária, gerada pelo sistema,
    aparece numa página própria, uma única vez. Ela não passa pelo framework de mensagens do
    admin, que grava em cookie ou na sessão do banco, e a resposta sai sem cache. A ação
    "Gerar nova senha temporária" serve a quem esqueceu a senha: não existe recuperação pelo
    próprio aluno, porque o sistema não envia e-mail.
    """

    add_form = InviteForm
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("username", "email")}),)
    list_display = ("username", "email", "is_active", "must_change_password", "is_staff")
    list_filter = ("is_active", "must_change_password", "is_staff", "is_superuser")
    actions = ["issue_new_temporary_password"]

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None:
            return fieldsets
        return [*fieldsets, ("Acesso", {"fields": ("must_change_password",)})]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser and super().has_add_permission(request)

    def has_issue_temporary_password_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser

    def save_model(self, request: HttpRequest, obj: User, form, change: bool) -> None:
        """Na criação, grava o acesso e gera a senha, guardada só na requisição em curso."""
        if change:
            super().save_model(request, obj, form, change)
            return
        obj.set_unusable_password()
        super().save_model(request, obj, form, change)
        request.issued_passwords = [(obj, issue_temporary_password(obj))]

    def response_add(self, request: HttpRequest, obj: User, post_url_continue=None):
        return self._password_page(request, request.issued_passwords)

    @admin.action(
        description="Gerar nova senha temporária",
        permissions=["issue_temporary_password"],
    )
    def issue_new_temporary_password(self, request: HttpRequest, queryset):
        issued = [(user, issue_temporary_password(user)) for user in queryset]
        return self._password_page(request, issued)

    def _password_page(self, request: HttpRequest, issued: list) -> HttpResponse:
        """A página que mostra cada senha uma única vez, sem permitir guardá-la em cache."""
        response = TemplateResponse(
            request,
            _TEMPORARY_PASSWORD_TEMPLATE,
            {
                **self.admin_site.each_context(request),
                "title": "Senha temporária",
                "issued": [(user.username, password) for user, password in issued],
                "opts": self.opts,
            },
        )
        add_never_cache_headers(response)
        return response
