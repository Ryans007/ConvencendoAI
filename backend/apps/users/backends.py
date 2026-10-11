from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied

from apps.users.services.client_ip import client_ip
from apps.users.services.login_lockout import login_lock_remaining_seconds


class LockoutModelBackend(ModelBackend):
    """Autentica como o padrão do Django, mas recusa antes de conferir a senha durante um bloqueio.

    Fica no `authenticate`, o ponto por onde passam o login do app e o do admin, então nenhum
    caminho escapa do bloqueio. Recusar antes de olhar a senha impede que a senha certa revele
    algo durante o bloqueio. O `PermissionDenied` faz o Django parar de tentar os outros
    backends e devolver `None`.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        username = username if username is not None else kwargs.get("username", "")
        if login_lock_remaining_seconds(username or "", client_ip(request)) > 0:
            raise PermissionDenied
        return super().authenticate(request, username=username, password=password, **kwargs)
