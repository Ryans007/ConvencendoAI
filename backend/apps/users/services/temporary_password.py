import secrets

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.users.services.refresh_tokens import revoke_refresh_tokens

PASSWORD_LENGTH = 12
_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz"
_DIGITS = "23456789"
_ALPHABET = _LETTERS + _DIGITS


def generate_temporary_password(user) -> str:
    """Gera uma senha temporária que passa nas regras de validação de senha do sistema.

    O alfabeto não tem os caracteres que se confundem ao ditar ou copiar (`0` e `O`, `1`, `l`
    e `I`), e a senha tem sempre ao menos uma letra e um número, então nunca é inteiramente
    numérica. Se a senha sorteada reprovar na validação, por exemplo por se parecer com o
    nome de usuário, sorteia outra.
    """
    while True:
        candidate = "".join(secrets.choice(_ALPHABET) for _ in range(PASSWORD_LENGTH))
        if not any(c in _LETTERS for c in candidate) or not any(c in _DIGITS for c in candidate):
            continue
        try:
            validate_password(candidate, user)
        except ValidationError:
            continue
        return candidate


def issue_temporary_password(user) -> str:
    """Troca a senha do usuário por uma temporária nova e a devolve, uma única vez.

    A senha só existe em texto na devolução desta função: no banco fica o hash. A troca passa
    a ser obrigatória, e as sessões abertas com a senha anterior são encerradas, porque quem
    esqueceu a senha, ou perdeu o aparelho, não pode continuar logado com ela.
    """
    password = generate_temporary_password(user)
    user.set_password(password)
    user.must_change_password = True
    user.save(update_fields=["password", "must_change_password"])
    revoke_refresh_tokens(user)
    return password
