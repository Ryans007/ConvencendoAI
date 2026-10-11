from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    """Usuário da aplicação.

    Só entra quem o super-admin criou. A senha temporária que ele entrega à pessoa vem com
    `must_change_password` ligado: enquanto a troca não acontece, a API e a sessão de voz
    recusam tudo, menos a própria troca e o logout.

    O e-mail é único sem diferenciar maiúsculas, mas só quando preenchido: os usuários
    anteriores ao convite não têm e-mail e continuam válidos. O login segue sendo pelo nome
    de usuário.
    """

    must_change_password = models.BooleanField(
        default=False,
        verbose_name="deve trocar a senha",
        help_text=(
            "Ligado quando a senha atual é temporária: a pessoa só consegue trocar a senha "
            "ou sair até defini-la."
        ),
    )

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=~models.Q(email=""),
                name="users_user_email_unique_ci",
                violation_error_message="Já existe um acesso com este e-mail.",
            ),
        ]
