import ipaddress

from django.conf import settings
from django.http import HttpRequest


def _valid(candidate: str) -> str | None:
    try:
        return str(ipaddress.ip_address(candidate.strip()))
    except ValueError:
        return None


def client_ip(request: HttpRequest | None) -> str | None:
    """O IP do cliente que fez o pedido, descontados os proxies confiáveis à frente do servidor.

    Sem proxy (`TRUSTED_PROXY_COUNT` 0, o desenvolvimento), vale o endereço da conexão. Atrás
    de proxies confiáveis, o IP real é o que está `TRUSTED_PROXY_COUNT` posições a partir do
    fim do `X-Forwarded-For`: cada proxy acrescenta ao fim o endereço de quem falou com ele, e
    o cliente só consegue escrever no começo da lista, nunca no fim. Ler o começo deixaria um
    atacante escolher o IP que o bloqueio vê. Se o cabeçalho tem menos entradas que os proxies
    esperados, o pedido não passou pela cadeia esperada, e vale o endereço da conexão.

    Um valor de `TRUSTED_PROXY_COUNT` maior que o real deixa o atacante forjar o IP; menor, ou
    zero atrás de um proxy, faz todos os alunos parecerem vir do IP do proxy.
    """
    if request is None:
        return None
    connection = _valid(request.META.get("REMOTE_ADDR", ""))
    proxies = settings.TRUSTED_PROXY_COUNT
    if proxies <= 0:
        return connection
    forwarded = [part for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if part]
    if len(forwarded) < proxies:
        return connection
    return _valid(forwarded[-proxies]) or connection
