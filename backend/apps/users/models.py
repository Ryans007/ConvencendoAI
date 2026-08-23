"""Modelos do dominio de usuario."""

from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Usuario da aplicacao.

    Nasce sem campos adicionais. Existe desde o inicio porque `AUTH_USER_MODEL` e a
    unica configuracao do Django que nao se troca depois sem migration manual custosa.
    Campos de perfil do aluno entram quando houver o dominio que os justifique.
    """
