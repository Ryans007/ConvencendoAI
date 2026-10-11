import re

import pytest
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.urls import reverse

pytestmark = pytest.mark.django_db

_PASSWORD_CELL = re.compile(r"<code>([^<]+)</code>")
_OLD_PASSWORD = "Xk9#mQ2vLp8Z"


@pytest.fixture
def superuser(django_user_model):
    return django_user_model.objects.create_superuser(
        username="chefe", email="chefe@empresa.com", password=_OLD_PASSWORD
    )


@pytest.fixture
def admin_client(client, superuser):
    client.force_login(superuser)
    return client


def _create(admin_client, username="maria", email="maria@empresa.com"):
    return admin_client.post(
        reverse("admin:users_user_add"), {"username": username, "email": email}
    )


def _shown_password(response) -> str:
    return _PASSWORD_CELL.search(response.content.decode()).group(1)


def test_creating_an_access_shows_the_temporary_password_and_the_person_can_log_in(
    admin_client, django_user_model
):
    response = _create(admin_client)

    assert response.status_code == 200
    password = _shown_password(response)
    user = django_user_model.objects.get(username="maria")
    assert user.is_active and user.must_change_password
    assert user.email == "maria@empresa.com"
    assert user.check_password(password)
    assert "não será mostrada de novo" in response.content.decode()


def test_the_password_is_never_in_the_database_the_messages_or_a_cache(
    admin_client, django_user_model
):
    response = _create(admin_client)
    password = _shown_password(response)

    user = django_user_model.objects.get(username="maria")
    assert password not in user.password
    assert not list(get_messages(response.wsgi_request))
    assert "no-cache" in response["Cache-Control"] or "no-store" in response["Cache-Control"]
    assert password not in str(dict(admin_client.session.items()))


def test_going_back_to_the_access_never_shows_the_password_again(admin_client, django_user_model):
    response = _create(admin_client)
    password = _shown_password(response)
    user = django_user_model.objects.get(username="maria")

    detail = admin_client.get(reverse("admin:users_user_change", args=[user.pk]))
    listing = admin_client.get(reverse("admin:users_user_changelist"))

    assert password not in detail.content.decode()
    assert password not in listing.content.decode()


def test_the_email_is_stored_in_lowercase(admin_client, django_user_model):
    _create(admin_client, email="Maria@Empresa.COM")

    assert django_user_model.objects.get(username="maria").email == "maria@empresa.com"


def test_an_email_already_in_use_is_refused_with_any_case(admin_client, django_user_model):
    django_user_model.objects.create_user(username="antiga", email="maria@empresa.com")

    response = _create(admin_client, username="outra", email="Maria@Empresa.com")

    assert response.status_code == 200
    assert "Já existe um acesso com este e-mail." in response.content.decode()
    assert not django_user_model.objects.filter(username="outra").exists()


def test_an_existing_username_is_refused_without_issuing_a_password(
    admin_client, django_user_model
):
    django_user_model.objects.create_user(username="maria", email="a@empresa.com")

    response = _create(admin_client, username="maria", email="b@empresa.com")

    assert _PASSWORD_CELL.search(response.content.decode()) is None
    assert django_user_model.objects.filter(username="maria").count() == 1


def test_the_new_password_action_replaces_the_password_of_each_chosen_access(
    admin_client, django_user_model
):
    maria = django_user_model.objects.create_user(
        username="maria", email="m@empresa.com", password=_OLD_PASSWORD
    )
    joao = django_user_model.objects.create_user(
        username="joao", email="j@empresa.com", password=_OLD_PASSWORD
    )

    response = admin_client.post(
        reverse("admin:users_user_changelist"),
        {
            "action": "issue_new_temporary_password",
            "_selected_action": [maria.pk, joao.pk],
        },
    )

    shown = _PASSWORD_CELL.findall(response.content.decode())
    assert len(shown) == 2
    maria.refresh_from_db()
    joao.refresh_from_db()
    assert not maria.check_password(_OLD_PASSWORD) and maria.must_change_password
    assert not joao.check_password(_OLD_PASSWORD) and joao.must_change_password
    assert any(maria.check_password(p) for p in shown)
    assert any(joao.check_password(p) for p in shown)


def test_a_staff_user_who_is_not_superuser_cannot_create_an_access_nor_issue_passwords(
    client, django_user_model
):
    staff = django_user_model.objects.create_user(
        username="equipe", password=_OLD_PASSWORD, is_staff=True
    )
    staff.user_permissions.set(Permission.objects.filter(content_type__app_label="users"))
    client.force_login(staff)
    target = django_user_model.objects.create_user(username="maria", email="m@empresa.com")

    add = client.get(reverse("admin:users_user_add"))
    action = client.post(
        reverse("admin:users_user_changelist"),
        {"action": "issue_new_temporary_password", "_selected_action": [target.pk]},
    )
    listing = client.get(reverse("admin:users_user_changelist"))

    assert add.status_code == 403
    assert not _PASSWORD_CELL.search(action.content.decode())
    assert "issue_new_temporary_password" not in listing.content.decode()
    target.refresh_from_db()
    assert not target.must_change_password
