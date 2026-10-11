from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from apps.users.models import LoginFailure
from apps.users.services.client_ip import client_ip
from apps.users.services.login_lockout import clear_login_failures, login_lock_remaining_seconds


@receiver(user_login_failed)
def record_login_failure(sender, credentials, request=None, **kwargs) -> None:
    """Grava a senha errada, sem a senha, a menos que o próprio bloqueio tenha recusado o pedido.

    O Django manda este sinal também quando o backend recusa por bloqueio. Gravar essas
    recusas renovaria o bloqueio a cada tentativa e o tornaria eterno enquanto o atacante
    insistisse, e travaria o aluno que só esperou pouco demais.
    """
    username = str(credentials.get("username", "") or "")
    ip_address = client_ip(request)
    if login_lock_remaining_seconds(username, ip_address) > 0:
        return
    LoginFailure.objects.create(username=username[:150], ip_address=ip_address)


@receiver(user_logged_in)
def forget_login_failures(sender, user, request=None, **kwargs) -> None:
    """Zera as senhas erradas do usuário quando ele entra, pelo admin ou por onde mais passe."""
    clear_login_failures(user.get_username())
