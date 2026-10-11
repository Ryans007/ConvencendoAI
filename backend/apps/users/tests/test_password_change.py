import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.services.temporary_password import issue_temporary_password

pytestmark = pytest.mark.django_db

_STRONG_PASSWORD = "Xk9#mQ2vLp8Z"
_NEW_PASSWORD = "Nova#Senha2026x"
_PROTECTED = "/api/journey/"


@pytest.fixture
def invited(django_user_model):
    """Um acesso recém-criado: senha temporária, troca obrigatória."""
    user = django_user_model.objects.create_user(username="maria", email="maria@empresa.com")
    return user, issue_temporary_password(user)


def _login(username: str, password: str):
    return APIClient().post("/api/auth/token/", {"username": username, "password": password})


def _authenticated(login_response) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}")
    return client


def test_login_with_the_temporary_password_says_the_change_is_mandatory(invited):
    user, temporary = invited

    response = _login("maria", temporary)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["must_change_password"] is True
    assert "access" in response.data and "refresh" in response.data


def test_login_of_who_already_chose_a_password_says_the_change_is_not_mandatory(
    django_user_model,
):
    django_user_model.objects.create_user(username="aluno", password=_STRONG_PASSWORD)

    response = _login("aluno", _STRONG_PASSWORD)

    assert response.data["must_change_password"] is False


def test_a_protected_route_is_refused_with_its_own_code_while_the_change_is_pending(invited):
    _, temporary = invited
    client = _authenticated(_login("maria", temporary))

    response = client.get(_PROTECTED)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "password_change_required"
    assert "tracks" not in response.data


def test_logout_still_works_while_the_change_is_pending(invited):
    _, temporary = invited
    login = _login("maria", temporary)
    client = _authenticated(login)

    response = client.post("/api/auth/logout/", {"refresh": login.data["refresh"]})

    assert response.status_code == status.HTTP_205_RESET_CONTENT


def test_a_user_without_a_pending_change_reaches_the_protected_route(django_user_model):
    django_user_model.objects.create_user(username="aluno", password=_STRONG_PASSWORD)
    client = _authenticated(_login("aluno", _STRONG_PASSWORD))

    assert client.get(_PROTECTED).status_code == status.HTTP_200_OK


def test_changing_the_password_clears_the_obligation_and_returns_new_tokens(invited):
    user, temporary = invited
    client = _authenticated(_login("maria", temporary))

    response = client.post(
        "/api/auth/password/", {"current_password": temporary, "new_password": _NEW_PASSWORD}
    )

    assert response.status_code == status.HTTP_200_OK
    user.refresh_from_db()
    assert user.must_change_password is False
    assert user.check_password(_NEW_PASSWORD)
    renewed = APIClient()
    renewed.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    assert renewed.get(_PROTECTED).status_code == status.HTTP_200_OK


def test_the_tokens_issued_before_the_change_stop_working(invited):
    _, temporary = invited
    login = _login("maria", temporary)
    client = _authenticated(login)

    client.post(
        "/api/auth/password/", {"current_password": temporary, "new_password": _NEW_PASSWORD}
    )

    assert client.get(_PROTECTED).status_code == status.HTTP_401_UNAUTHORIZED
    renewal = APIClient().post("/api/auth/token/refresh/", {"refresh": login.data["refresh"]})
    assert renewal.status_code == status.HTTP_401_UNAUTHORIZED


def test_the_old_temporary_password_no_longer_logs_in_after_the_change(invited):
    _, temporary = invited
    client = _authenticated(_login("maria", temporary))

    client.post(
        "/api/auth/password/", {"current_password": temporary, "new_password": _NEW_PASSWORD}
    )

    assert _login("maria", temporary).status_code == status.HTTP_401_UNAUTHORIZED
    assert _login("maria", _NEW_PASSWORD).status_code == status.HTTP_200_OK


def test_a_wrong_current_password_is_refused_without_changing_anything(invited):
    user, temporary = invited
    client = _authenticated(_login("maria", temporary))

    response = client.post(
        "/api/auth/password/", {"current_password": "errada", "new_password": _NEW_PASSWORD}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "current_password" in response.data
    user.refresh_from_db()
    assert user.check_password(temporary) and user.must_change_password


def test_a_new_password_equal_to_the_current_one_is_refused(invited):
    _, temporary = invited
    client = _authenticated(_login("maria", temporary))

    response = client.post(
        "/api/auth/password/", {"current_password": temporary, "new_password": temporary}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "A senha nova não pode ser igual à atual." in response.data["new_password"]


def test_a_weak_new_password_is_refused_with_the_reason(invited):
    user, temporary = invited
    client = _authenticated(_login("maria", temporary))

    response = client.post(
        "/api/auth/password/", {"current_password": temporary, "new_password": "password"}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["new_password"]
    user.refresh_from_db()
    assert user.check_password(temporary)


def test_changing_the_password_requires_authentication():
    response = APIClient().post(
        "/api/auth/password/", {"current_password": "a", "new_password": "b"}
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_a_deactivated_access_cannot_log_in(django_user_model):
    user = django_user_model.objects.create_user(username="aluno", password=_STRONG_PASSWORD)
    user.is_active = False
    user.save(update_fields=["is_active"])

    assert _login("aluno", _STRONG_PASSWORD).status_code == status.HTTP_401_UNAUTHORIZED


def test_the_register_endpoint_no_longer_exists():
    response = APIClient().post(
        "/api/auth/register/", {"username": "novo", "password": _STRONG_PASSWORD}
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_issuing_a_new_temporary_password_ends_the_open_session(django_user_model):
    user = django_user_model.objects.create_user(username="aluno", password=_STRONG_PASSWORD)
    login = _login("aluno", _STRONG_PASSWORD)
    client = _authenticated(login)
    assert client.get(_PROTECTED).status_code == status.HTTP_200_OK

    issue_temporary_password(user)

    assert client.get(_PROTECTED).status_code == status.HTTP_401_UNAUTHORIZED
    renewal = APIClient().post("/api/auth/token/refresh/", {"refresh": login.data["refresh"]})
    assert renewal.status_code == status.HTTP_401_UNAUTHORIZED
