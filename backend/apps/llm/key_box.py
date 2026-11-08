import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

_DOMAIN = b"convencendoai.llm-provider-key:"


def _fernet() -> Fernet:
    """A chave Fernet derivada do `SECRET_KEY` com o prefixo `_DOMAIN`.

    O prefixo separa esta derivação de qualquer outro uso do `SECRET_KEY`: a mesma chave
    secreta, com outro prefixo, dá outra chave Fernet.
    """
    digest = hashlib.sha256(_DOMAIN + settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def seal(plain: str) -> str:
    """Criptografa a chave de um provedor para gravar no banco. O vazio continua vazio.

    A chave Fernet é derivada do `SECRET_KEY`, então nenhuma configuração nova é necessária, e um
    dump do banco sem o `SECRET_KEY` não revela a chave.
    """
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode()).decode()


def open_sealed(token: str) -> str:
    """Decifra o que `seal` gravou, ou devolve vazio se o token não decifra.

    Um token ilegível, por exemplo depois de trocar o `SECRET_KEY`, vale como chave ausente: o
    provedor passa a ser tratado como não configurado, sem erro 500, e o admin mostra "não
    definida" até a chave ser cadastrada de novo.
    """
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""
