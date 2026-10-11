import pytest
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.services.temporary_password import (
    PASSWORD_LENGTH,
    generate_temporary_password,
    issue_temporary_password,
)

pytestmark = pytest.mark.django_db

_AMBIGUOUS = set("0O1lI")


def _user(django_user_model, password: str = "Xk9#mQ2vLp8Z"):
    return django_user_model.objects.create_user(username="maria", password=password)


def test_the_generated_password_passes_the_validation_and_has_the_expected_shape(
    django_user_model,
):
    user = _user(django_user_model)

    for _ in range(50):
        password = generate_temporary_password(user)

        validate_password(password, user)
        assert len(password) == PASSWORD_LENGTH
        assert not (set(password) & _AMBIGUOUS)
        assert any(c.isalpha() for c in password) and any(c.isdigit() for c in password)


def test_each_generated_password_is_different(django_user_model):
    user = _user(django_user_model)

    assert len({generate_temporary_password(user) for _ in range(20)}) == 20


def test_issuing_replaces_the_password_and_makes_the_change_mandatory(django_user_model):
    user = _user(django_user_model)

    password = issue_temporary_password(user)

    user.refresh_from_db()
    assert user.check_password(password)
    assert not user.check_password("Xk9#mQ2vLp8Z")
    assert user.must_change_password is True


def test_the_temporary_password_is_stored_only_as_a_hash(django_user_model):
    user = _user(django_user_model)

    password = issue_temporary_password(user)

    user.refresh_from_db()
    assert password not in user.password
    assert user.password.startswith(("pbkdf2_", "argon2", "bcrypt", "scrypt"))


def test_issuing_blocks_the_refresh_tokens_that_were_already_out(django_user_model):
    user = _user(django_user_model)
    first = RefreshToken.for_user(user)
    second = RefreshToken.for_user(user)

    issue_temporary_password(user)

    assert BlacklistedToken.objects.filter(token__user=user).count() == 2
    for token in (first, second):
        assert BlacklistedToken.objects.filter(token__jti=token["jti"]).exists()


def test_issuing_does_not_touch_the_tokens_of_another_user(django_user_model):
    user = _user(django_user_model)
    other = django_user_model.objects.create_user(username="outro", password="Xk9#mQ2vLp8Z")
    RefreshToken.for_user(other)

    issue_temporary_password(user)

    assert not BlacklistedToken.objects.filter(token__user=other).exists()
