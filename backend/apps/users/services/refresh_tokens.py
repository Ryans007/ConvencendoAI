from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken


def revoke_refresh_tokens(user) -> int:
    """Bloqueia todos os tokens de renovação do usuário e devolve quantos foram bloqueados.

    A troca de senha e a nova senha temporária encerram as sessões abertas: sem isso, quem
    tinha um token de renovação continuaria renovando o acesso com a senha antiga já morta.
    Os tokens de acesso caem pela revogação por senha, que compara um hash da senha gravado
    no próprio token, mas a renovação não faz essa comparação.
    """
    revoked = 0
    for outstanding in OutstandingToken.objects.filter(user=user):
        _, created = BlacklistedToken.objects.get_or_create(token=outstanding)
        revoked += int(created)
    return revoked
