import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.usage.models import AccessLimits

pytestmark = pytest.mark.django_db

_PASSWORD = "Xk9#mQ2vLp8Z"


@pytest.fixture
def superuser(django_user_model):
    return django_user_model.objects.create_superuser(
        username="chefe", email="chefe@empresa.com", password=_PASSWORD
    )


def test_the_defaults_are_the_ones_of_the_spec():
    limits = AccessLimits.get_solo()

    assert limits.login_max_failures_per_user == 5
    assert limits.login_max_failures_per_ip == 20
    assert limits.login_window_minutes == 15
    assert limits.login_lockout_minutes == 15
    assert limits.max_open_voice_sessions == 1
    assert limits.max_voice_sessions_per_day == 20
    assert limits.max_turn_audio_kb == 2048
    assert limits.max_review_calls_per_minute == 20


def test_the_configuration_is_a_single_row_that_cannot_be_deleted():
    first = AccessLimits.get_solo()
    AccessLimits(login_max_failures_per_user=9).save()

    assert AccessLimits.objects.count() == 1
    assert AccessLimits.get_solo().pk == first.pk == 1
    with pytest.raises(RuntimeError):
        AccessLimits.get_solo().delete()


def test_a_change_is_read_on_the_next_call():
    limits = AccessLimits.get_solo()
    limits.max_voice_sessions_per_day = 10
    limits.save()

    assert AccessLimits.get_solo().max_voice_sessions_per_day == 10


def test_the_superuser_edits_the_limits_in_the_admin(client, superuser):
    AccessLimits.get_solo()
    client.force_login(superuser)
    url = reverse("admin:usage_accesslimits_change", args=[1])
    form = {
        "login_max_failures_per_user": 3,
        "login_max_failures_per_ip": 20,
        "login_window_minutes": 15,
        "login_lockout_minutes": 30,
        "max_open_voice_sessions": 1,
        "max_voice_sessions_per_day": 10,
        "max_turn_audio_kb": 2048,
        "max_review_calls_per_minute": 20,
    }

    response = client.post(url, form)

    assert response.status_code == 302
    limits = AccessLimits.get_solo()
    assert (limits.login_max_failures_per_user, limits.login_lockout_minutes) == (3, 30)


def test_a_staff_user_who_is_not_superuser_does_not_see_the_limits(client, django_user_model):
    AccessLimits.get_solo()
    staff = django_user_model.objects.create_user(
        username="equipe", password=_PASSWORD, is_staff=True
    )
    staff.user_permissions.set(Permission.objects.filter(content_type__app_label="usage"))
    client.force_login(staff)

    change = client.get(reverse("admin:usage_accesslimits_change", args=[1]))
    index = client.get(reverse("admin:index")).content.decode().lower()

    assert change.status_code == 403
    assert "limites de acesso" not in index
