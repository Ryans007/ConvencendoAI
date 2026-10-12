from django.test import RequestFactory, override_settings

from apps.users.services.client_ip import client_ip

TRAEFIK_IP = "172.18.0.2"
NGINX_IP = "172.19.0.3"
REAL_CLIENT_IP = "203.0.113.9"


def _request(forwarded_for: str):
    return RequestFactory().get(
        "/api/auth/token/", HTTP_X_FORWARDED_FOR=forwarded_for, REMOTE_ADDR=NGINX_IP
    )


@override_settings(TRUSTED_PROXY_COUNT=2)
def test_the_real_ip_is_found_behind_traefik_and_nginx() -> None:
    """O Traefik acrescenta o IP do aluno e o nginx o do Traefik: o real fica em segundo, do fim."""
    assert client_ip(_request(f"{REAL_CLIENT_IP}, {TRAEFIK_IP}")) == REAL_CLIENT_IP


@override_settings(TRUSTED_PROXY_COUNT=2)
def test_an_ip_forged_by_the_client_does_not_decide() -> None:
    """O que o cliente escreve fica no começo da lista, e o bloqueio lê a partir do fim."""
    forged = f"6.6.6.6, {REAL_CLIENT_IP}, {TRAEFIK_IP}"

    assert client_ip(_request(forged)) == REAL_CLIENT_IP
