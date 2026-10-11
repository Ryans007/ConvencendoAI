import math

from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm

from apps.users.services.client_ip import client_ip
from apps.users.services.login_lockout import login_lock_remaining_seconds


class LockoutAdminAuthenticationForm(AdminAuthenticationForm):
    """O login do admin, recusando com uma mensagem clara quando o usuário ou o IP estão bloqueados.

    O bloqueio em si é do backend de autenticação, que recusa antes de conferir a senha; sem
    este formulário o admin diria só "usuário ou senha incorretos", e quem esperou o tempo
    certo não saberia por que não entra.
    """

    def clean(self):
        username = self.data.get(self.add_prefix("username"), "") or ""
        remaining = login_lock_remaining_seconds(username, client_ip(self.request))
        if remaining > 0:
            minutes = math.ceil(remaining / 60)
            raise forms.ValidationError(
                "Muitas tentativas de login. Tente de novo em %(minutes)s minuto(s).",
                code="login_locked",
                params={"minutes": minutes},
            )
        return super().clean()
