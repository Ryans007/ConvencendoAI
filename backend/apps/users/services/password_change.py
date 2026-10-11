from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.services.refresh_tokens import revoke_refresh_tokens


def change_password(user, new_password: str) -> RefreshToken:
    """Grava a senha nova, encerra as sessões antigas e devolve a sessão nova do aluno.

    Desliga a troca obrigatória, bloqueia todos os tokens de renovação emitidos antes e só
    depois emite o par novo: o token de acesso leva um hash da senha, então um emitido antes
    da troca é recusado, e o emitido agora já sai com o hash da senha nova. Assim o aluno
    segue de onde estava, sem entrar de novo, e uma senha temporária interceptada não serve
    a mais ninguém depois do primeiro uso.
    """
    user.set_password(new_password)
    user.must_change_password = False
    user.save(update_fields=["password", "must_change_password"])
    revoke_refresh_tokens(user)
    return RefreshToken.for_user(user)
