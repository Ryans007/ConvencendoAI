from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import LoginFailure
from apps.users.services.client_ip import client_ip
from apps.users.services.login_lockout import login_lock_remaining_seconds

pytestmark = pytest.mark.django_db

_PASSWORD = "Xk9#mQ2vLp8Z"


@pytest.fixture
def maria(django_user_model):
    return django_user_model.objects.create_user(username="maria", password=_PASSWORD)


def _login(username: str, password: str, client: APIClient | None = None, **extra):
    return (client or APIClient()).post(
        "/api/auth/token/", {"username": username, "password": password}, **extra
    )


def _fail(username: str, ip: str = "127.0.0.1", minutes_ago: float = 0) -> LoginFailure:
    row = LoginFailure.objects.create(username=username, ip_address=ip)
    if minutes_ago:
        LoginFailure.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - timedelta(minutes=minutes_ago)
        )
    return row


def test_four_wrong_passwords_do_not_lock_yet(maria):
    for _ in range(4):
        assert _login("maria", "errada").status_code == status.HTTP_401_UNAUTHORIZED

    assert _login("maria", _PASSWORD).status_code == status.HTTP_200_OK


def test_the_fifth_wrong_password_locks_even_the_right_password_out(maria):
    for _ in range(5):
        _login("maria", "errada")

    response = _login("maria", _PASSWORD)

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.data["code"] == "login_locked"
    assert 0 < response.data["retry_after_seconds"] <= 15 * 60
    assert response["Retry-After"] == str(response.data["retry_after_seconds"])
    assert "access" not in response.data


def test_the_attempts_refused_by_the_lock_do_not_renew_it(maria):
    for _ in range(5):
        _login("maria", "errada")
    recorded = LoginFailure.objects.count()

    for _ in range(4):
        assert _login("maria", "errada").status_code == status.HTTP_429_TOO_MANY_REQUESTS

    assert LoginFailure.objects.count() == recorded


def test_an_unknown_username_is_locked_the_same_way_so_nothing_is_revealed(db):
    for _ in range(5):
        _login("naoexiste", "errada")

    response = _login("naoexiste", "errada")

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.data["code"] == "login_locked"


def test_twenty_wrong_passwords_from_one_ip_lock_the_ip_for_every_user(maria):
    for number in range(20):
        _fail(f"usuario{number}", ip="127.0.0.1")

    response = _login("maria", _PASSWORD)

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_failures_from_another_ip_do_not_lock_this_one(maria):
    for number in range(20):
        _fail(f"usuario{number}", ip="203.0.113.9")

    assert _login("maria", _PASSWORD).status_code == status.HTTP_200_OK


def test_the_lock_ends_after_the_lockout_time(maria):
    for _ in range(5):
        _fail("maria", minutes_ago=16)

    assert _login("maria", _PASSWORD).status_code == status.HTTP_200_OK


def test_failures_older_than_the_window_do_not_add_up(maria):
    for _ in range(4):
        _fail("maria", minutes_ago=30)
    _fail("maria", minutes_ago=1)

    assert login_lock_remaining_seconds("maria", "127.0.0.1") == 0


def test_a_right_login_clears_the_wrong_passwords_of_that_user(maria):
    for _ in range(3):
        _login("maria", "errada")
    assert LoginFailure.objects.filter(username="maria").count() == 3

    assert _login("maria", _PASSWORD).status_code == status.HTTP_200_OK

    assert not LoginFailure.objects.filter(username="maria").exists()


def test_the_password_is_never_stored(maria):
    _login("maria", "SenhaSecretaErrada#1")

    failure = LoginFailure.objects.get()
    stored = " ".join(str(getattr(failure, f.name)) for f in LoginFailure._meta.fields)
    assert "SenhaSecretaErrada#1" not in stored
    assert failure.username == "maria"


def test_the_admin_login_locks_with_a_clear_message(client, django_user_model):
    django_user_model.objects.create_superuser(
        username="chefe", email="c@empresa.com", password=_PASSWORD
    )
    url = reverse("admin:login")
    for _ in range(5):
        client.post(url, {"username": "chefe", "password": "errada", "next": "/admin/"})

    response = client.post(url, {"username": "chefe", "password": _PASSWORD, "next": "/admin/"})

    assert response.status_code == 200
    assert "Muitas tentativas de login" in response.content.decode()
    assert "_auth_user_id" not in client.session


def test_a_right_admin_login_clears_the_wrong_passwords(client, django_user_model):
    django_user_model.objects.create_superuser(
        username="chefe", email="c@empresa.com", password=_PASSWORD
    )
    url = reverse("admin:login")
    client.post(url, {"username": "chefe", "password": "errada", "next": "/admin/"})
    assert LoginFailure.objects.filter(username="chefe").exists()

    client.post(url, {"username": "chefe", "password": _PASSWORD, "next": "/admin/"})

    assert not LoginFailure.objects.filter(username="chefe").exists()


def test_the_failures_screen_is_read_only_and_only_for_the_superuser(client, django_user_model):
    _fail("alguem")
    staff = django_user_model.objects.create_user(
        username="equipe", password=_PASSWORD, is_staff=True
    )
    boss = django_user_model.objects.create_superuser(
        username="chefe", email="c@empresa.com", password=_PASSWORD
    )

    client.force_login(staff)
    assert client.get(reverse("admin:users_loginfailure_changelist")).status_code == 403

    client.force_login(boss)
    page = client.get(reverse("admin:users_loginfailure_changelist"))
    assert page.status_code == 200 and "alguem" in page.content.decode()
    assert client.post(reverse("admin:users_loginfailure_add"), {}).status_code == 403


def _request(remote: str, forwarded: str | None = None):
    extra = {"REMOTE_ADDR": remote}
    if forwarded is not None:
        extra["HTTP_X_FORWARDED_FOR"] = forwarded
    return RequestFactory().get("/", **extra)


def test_without_trusted_proxies_the_forwarded_header_is_ignored(settings):
    settings.TRUSTED_PROXY_COUNT = 0

    assert client_ip(_request("10.0.0.5", "1.2.3.4")) == "10.0.0.5"


def test_behind_one_proxy_the_ip_is_the_last_entry_the_proxy_added(settings):
    settings.TRUSTED_PROXY_COUNT = 1

    assert client_ip(_request("10.0.0.5", "198.51.100.7")) == "198.51.100.7"


def test_a_forged_first_entry_never_decides_the_ip(settings):
    settings.TRUSTED_PROXY_COUNT = 1

    assert client_ip(_request("10.0.0.5", "6.6.6.6, 198.51.100.7")) == "198.51.100.7"


def test_with_two_proxies_the_ip_is_the_second_from_the_end(settings):
    settings.TRUSTED_PROXY_COUNT = 2

    assert client_ip(_request("10.0.0.5", "6.6.6.6, 198.51.100.7, 10.0.0.9")) == "198.51.100.7"


def test_a_header_shorter_than_the_proxy_chain_falls_back_to_the_connection(settings):
    settings.TRUSTED_PROXY_COUNT = 2

    assert client_ip(_request("10.0.0.5", "198.51.100.7")) == "10.0.0.5"


def test_an_invalid_forwarded_value_falls_back_to_the_connection(settings):
    settings.TRUSTED_PROXY_COUNT = 1

    assert client_ip(_request("10.0.0.5", "nao-e-um-ip")) == "10.0.0.5"


def test_the_lock_uses_the_real_ip_behind_the_proxy(settings, maria):
    settings.TRUSTED_PROXY_COUNT = 1
    for number in range(20):
        _fail(f"u{number}", ip="198.51.100.7")

    blocked = _login("maria", _PASSWORD, REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR="198.51.100.7")
    other = _login("maria", _PASSWORD, REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR="198.51.100.8")

    assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert other.status_code == status.HTTP_200_OK
