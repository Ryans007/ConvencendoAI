from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.utils.cache import add_never_cache_headers
from django.utils.html import format_html, format_html_join

from apps.users.admin.forms import InviteForm
from apps.users.models import User
from apps.usage.services.student_statistics import annotate_list_statistics, student_statistics
from apps.usage.services.usage_totals import month_start, usage_breakdown
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

    O superuser também vê as estatísticas de uso de cada aluno: colunas na lista, calculadas
    numa consulta só, e uma seção somente leitura no detalhe. Para os demais usuários da equipe
    nada disso aparece.
    """

    _STATISTICS_COLUMNS = (
        "sessions_started_column",
        "sessions_completed_column",
        "scenarios_practiced_column",
        "average_score_column",
        "month_tokens_column",
        "month_cost_column",
    )

    add_form = InviteForm
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("username", "email")}),)
    list_display = ("username", "email", "is_active", "must_change_password", "is_staff")
    list_filter = ("is_active", "must_change_password", "is_staff", "is_superuser")
    actions = ["issue_new_temporary_password"]

    def get_queryset(self, request: HttpRequest):
        queryset = super().get_queryset(request)
        return annotate_list_statistics(queryset) if request.user.is_superuser else queryset

    def get_list_display(self, request: HttpRequest):
        columns = super().get_list_display(request)
        return (*columns, *self._STATISTICS_COLUMNS) if request.user.is_superuser else columns

    def get_readonly_fields(self, request: HttpRequest, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj is not None and request.user.is_superuser:
            return (*fields, "statistics")
        return fields

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None:
            return fieldsets
        extra = [("Acesso", {"fields": ("must_change_password",)})]
        if request.user.is_superuser:
            extra.append(("Estatísticas", {"fields": ("statistics",)}))
        return [*fieldsets, *extra]

    @admin.display(description="Sessões", ordering="sessions_started")
    def sessions_started_column(self, obj: User) -> int:
        return obj.sessions_started

    @admin.display(description="Concluídas", ordering="sessions_completed")
    def sessions_completed_column(self, obj: User) -> int:
        return obj.sessions_completed

    @admin.display(description="Cenários", ordering="scenarios_practiced")
    def scenarios_practiced_column(self, obj: User) -> int:
        return obj.scenarios_practiced

    @admin.display(description="Nota média", ordering="average_score")
    def average_score_column(self, obj: User) -> str:
        return f"{obj.average_score:.0f}" if obj.average_score is not None else "-"

    @admin.display(description="Tokens no mês", ordering="month_tokens")
    def month_tokens_column(self, obj: User) -> int:
        return obj.month_tokens

    @admin.display(description="Custo no mês (US$)", ordering="month_cost")
    def month_cost_column(self, obj: User) -> str:
        return f"{obj.month_cost:.4f}"

    @staticmethod
    def _usage_table(title: str, rows):
        """Uma tabela de uso de modelos por papel e modelo, com o custo estimado em dólar."""
        body = format_html_join(
            "",
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td>"
            "<td>{}</td><td>{}</td></tr>",
            (
                (
                    row.purpose,
                    row.model_id,
                    row.calls,
                    row.input_tokens,
                    row.output_tokens,
                    f"{row.billed_audio_seconds:.1f}",
                    row.characters,
                    f"{row.cost_usd:.6f}" + (" *" if row.unpriced_calls else ""),
                )
                for row in rows
            ),
        )
        return format_html(
            "<h4>{}</h4><table><tr><th>Papel</th><th>Modelo</th><th>Chamadas</th>"
            "<th>Tokens de entrada</th><th>Tokens de saída</th><th>Segundos cobrados</th>"
            "<th>Caracteres</th><th>Custo estimado (US$)</th></tr>{}</table>",
            title,
            body,
        )

    @admin.display(description="Estatísticas de uso")
    def statistics(self, obj: User):
        """O quadro de estatísticas do aluno, só números calculados do que já está gravado."""
        stats = student_statistics(obj)
        average = f"{stats.average_score:.1f}" if stats.average_score is not None else "-"
        last = stats.last_activity.strftime("%d/%m/%Y %H:%M") if stats.last_activity else "-"
        rows = [
            ("Sessões iniciadas", stats.sessions_started),
            ("Sessões concluídas", stats.sessions_completed),
            ("Sessões abandonadas", stats.sessions_abandoned),
            ("Cenários praticados", stats.scenarios_practiced),
            ("Combinações de cenário e nível", stats.levels_practiced),
            ("Nota média das concluídas", average),
            ("Aprovações", stats.approvals),
            ("Dicas usadas", stats.hints_used),
            ("Respostas na revisão", stats.review_answers),
            ("Itens revisados", stats.review_items_reviewed),
            ("Itens acertados na revisão", stats.review_hits),
            ("Última atividade", last),
        ]
        return format_html(
            "<table>{}</table>{}{}<p>* inclui chamadas de modelo sem preço cadastrado, "
            "cujo custo é desconhecido. Os custos são estimativas; a fatura do provedor é a "
            "fonte oficial.</p>",
            format_html_join("", "<tr><th>{}</th><td>{}</td></tr>", rows),
            self._usage_table("Uso de modelos neste mês", usage_breakdown(obj, month_start())),
            self._usage_table("Uso de modelos em todo o período", usage_breakdown(obj)),
        )

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
