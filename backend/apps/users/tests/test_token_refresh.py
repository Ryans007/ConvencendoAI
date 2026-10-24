import threading

import pytest
from django.db import connection, connections
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APIClient

_STRONG_PASSWORD = "Xk9#mQ2vLp8Z"


def _login(django_user_model) -> str:
    django_user_model.objects.create_user(username="aluno", password=_STRONG_PASSWORD)
    response = APIClient().post(
        "/api/auth/token/", {"username": "aluno", "password": _STRONG_PASSWORD}
    )
    return response.data["refresh"]


def _renew(refresh: str):
    return APIClient().post("/api/auth/token/refresh/", {"refresh": refresh})


@pytest.mark.django_db
def test_a_valid_token_gets_a_new_pair(django_user_model):
    refresh = _login(django_user_model)

    response = _renew(refresh)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["access"]
    assert response.data["refresh"] != refresh


@pytest.mark.django_db
def test_a_token_used_by_another_renewal_is_refused_with_401(django_user_model):
    refresh = _login(django_user_model)
    _renew(refresh)

    response = _renew(refresh)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_an_unreadable_token_is_refused_with_401(django_user_model):
    _login(django_user_model)

    response = _renew("not-a-token")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_the_renewal_locks_the_token_before_validating(django_user_model):
    refresh = _login(django_user_model)

    with CaptureQueriesContext(connection) as queries:
        _renew(refresh)

    statements = [query["sql"] for query in queries.captured_queries]
    lock = next(index for index, sql in enumerate(statements) if "FOR UPDATE" in sql)
    blacklist = next(
        index for index, sql in enumerate(statements) if "token_blacklist_blacklistedtoken" in sql
    )
    assert "token_blacklist_outstandingtoken" in statements[lock]
    assert lock < blacklist


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_simultaneous_renewals_with_the_same_token_never_fail_on_the_server(
    django_user_model,
):
    refresh = _login(django_user_model)
    start = threading.Barrier(2)
    codes: list[int] = []

    def renew() -> None:
        try:
            start.wait()
            codes.append(_renew(refresh).status_code)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=renew) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(codes) == [status.HTTP_200_OK, status.HTTP_401_UNAUTHORIZED]
