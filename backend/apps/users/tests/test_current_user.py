import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.services.temporary_password import issue_temporary_password

pytestmark = pytest.mark.django_db


def test_the_authenticated_user_gets_the_username(django_user_model):
    user = django_user_model.objects.create_user(username="maria", password="Xk9#mQ2vLp8Z")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/auth/me/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data == {"username": "maria"}


def test_the_current_user_requires_authentication():
    assert APIClient().get("/api/auth/me/").status_code == status.HTTP_401_UNAUTHORIZED


def test_the_current_user_is_blocked_while_the_password_change_is_pending(django_user_model):
    user = django_user_model.objects.create_user(username="maria")
    issue_temporary_password(user)
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/auth/me/")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "password_change_required"
