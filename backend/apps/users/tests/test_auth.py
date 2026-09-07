import pytest
from rest_framework import status
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

_STRONG_PASSWORD = "Xk9#mQ2vLp8Z"


def test_register_creates_account_and_authenticates_immediately():
    client = APIClient()

    response = client.post(
        "/api/auth/register/", {"username": "aluno", "password": _STRONG_PASSWORD}
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert "access" in response.data
    assert "refresh" in response.data


def test_register_rejects_duplicate_username(django_user_model):
    django_user_model.objects.create_user(username="aluno", password=_STRONG_PASSWORD)
    client = APIClient()

    response = client.post(
        "/api/auth/register/", {"username": "aluno", "password": _STRONG_PASSWORD}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert django_user_model.objects.filter(username="aluno").count() == 1


def test_register_rejects_weak_password(django_user_model):
    client = APIClient()

    response = client.post("/api/auth/register/", {"username": "aluno", "password": "password"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not django_user_model.objects.filter(username="aluno").exists()


def test_login_with_correct_credentials(django_user_model):
    django_user_model.objects.create_user(username="aluno", password=_STRONG_PASSWORD)
    client = APIClient()

    response = client.post(
        "/api/auth/token/", {"username": "aluno", "password": _STRONG_PASSWORD}
    )

    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert "refresh" in response.data


def test_login_with_incorrect_credentials_is_rejected(django_user_model):
    django_user_model.objects.create_user(username="aluno", password=_STRONG_PASSWORD)
    client = APIClient()

    response = client.post("/api/auth/token/", {"username": "aluno", "password": "wrong"})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_refresh_rotates_and_blacklists_the_previous_token(django_user_model):
    django_user_model.objects.create_user(username="aluno", password=_STRONG_PASSWORD)
    client = APIClient()
    login = client.post("/api/auth/token/", {"username": "aluno", "password": _STRONG_PASSWORD})
    first_refresh = login.data["refresh"]

    renewed = client.post("/api/auth/token/refresh/", {"refresh": first_refresh})
    assert renewed.status_code == status.HTTP_200_OK
    assert "access" in renewed.data
    assert "refresh" in renewed.data
    assert renewed.data["refresh"] != first_refresh

    reused = client.post("/api/auth/token/refresh/", {"refresh": first_refresh})
    assert reused.status_code == status.HTTP_401_UNAUTHORIZED


def test_logout_blacklists_the_given_token(django_user_model):
    user = django_user_model.objects.create_user(username="aluno", password=_STRONG_PASSWORD)
    client = APIClient()
    login = client.post("/api/auth/token/", {"username": "aluno", "password": _STRONG_PASSWORD})
    refresh_token = login.data["refresh"]

    client.force_authenticate(user=user)
    response = client.post("/api/auth/logout/", {"refresh": refresh_token})
    assert response.status_code == status.HTTP_205_RESET_CONTENT

    client.force_authenticate(user=None)
    reused = client.post("/api/auth/token/refresh/", {"refresh": refresh_token})
    assert reused.status_code == status.HTTP_401_UNAUTHORIZED


def test_protected_endpoint_without_token_is_rejected():
    client = APIClient()

    response = client.post("/api/auth/logout/", {"refresh": "whatever"})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
