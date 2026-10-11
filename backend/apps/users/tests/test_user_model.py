import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

pytestmark = pytest.mark.django_db


def test_a_new_user_does_not_have_to_change_the_password(django_user_model):
    user = django_user_model.objects.create_user(username="aluno", password="Xk9#mQ2vLp8Z")

    assert user.must_change_password is False


def test_two_emails_that_differ_only_in_case_are_refused_by_the_database(django_user_model):
    django_user_model.objects.create_user(username="maria", email="maria@empresa.com")

    with pytest.raises(IntegrityError), transaction.atomic():
        django_user_model.objects.create_user(username="outra", email="Maria@Empresa.com")


def test_the_validation_message_says_the_email_is_already_in_use(django_user_model):
    django_user_model.objects.create_user(username="maria", email="maria@empresa.com")
    duplicate = django_user_model(username="outra", email="MARIA@empresa.com")

    with pytest.raises(ValidationError) as error:
        duplicate.validate_constraints()

    assert "Já existe um acesso com este e-mail." in str(error.value)


def test_users_without_an_email_do_not_conflict_with_each_other(django_user_model):
    django_user_model.objects.create_user(username="antigo1", email="")
    django_user_model.objects.create_user(username="antigo2", email="")

    assert django_user_model.objects.filter(email="").count() == 2
