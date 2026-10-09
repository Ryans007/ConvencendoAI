from datetime import date

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.llm.models import AgentModelConfig
from apps.llm.services.factory import ModelNotConfigured
from apps.review.models import ReviewAnswer, ReviewItem
from apps.review.services import listening

pytestmark = pytest.mark.django_db

FORM = "I worked there yesterday."


@pytest.fixture
def student(django_user_model):
    return django_user_model.objects.create_user(username="aluno", password="Xk9#mQ2vLp8Z")


@pytest.fixture
def client(student):
    api_client = APIClient()
    api_client.force_authenticate(user=student)
    return api_client


@pytest.fixture
def spoken(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_synthesize(text: str, voice: str) -> bytes:
        calls.append((text, voice))
        return b"RIFF-fake-wav"

    monkeypatch.setattr(listening, "synthesize", fake_synthesize)
    return calls


def _answer(user, revealed: str = FORM) -> ReviewAnswer:
    item = ReviewItem.objects.create(user=user, rule="regra", box=0, due_on=date(2026, 10, 8))
    return ReviewAnswer.objects.create(
        item=item,
        step=1,
        attempt=1,
        heard="x",
        correct=True,
        feedback="ok",
        revealed_correct=revealed,
    )


def _url(answer: ReviewAnswer) -> str:
    return f"/api/review/answers/{answer.pk}/audio/"


def test_the_revealed_correct_form_is_spoken_with_the_review_voice(client, student, spoken):
    answer = _answer(student)

    response = client.get(_url(answer))

    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"] == "audio/wav"
    assert response.content == b"RIFF-fake-wav"
    assert response["Cache-Control"] == "private, max-age=3600"
    assert spoken == [(FORM, "hannah")]


def test_changing_the_voice_in_the_config_changes_the_next_audio(client, student, spoken):
    config = AgentModelConfig.get_solo()
    config.review_voice = "troy"
    config.save()
    answer = _answer(student)

    client.get(_url(answer))

    assert spoken == [(FORM, "troy")]


def test_a_client_asking_for_audio_is_not_refused_for_its_accept_header(client, student, spoken):
    answer = _answer(student)

    response = client.get(_url(answer), HTTP_ACCEPT="audio/wav")

    assert response.status_code == status.HTTP_200_OK


def test_an_answer_with_nothing_revealed_is_not_found_and_never_spoken(client, student, spoken):
    answer = _answer(student, revealed="")

    response = client.get(_url(answer))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert spoken == []


def test_another_students_answer_is_not_found(client, django_user_model, spoken):
    other = django_user_model.objects.create_user(username="outro", password="Xk9#mQ2vLp8Z")
    answer = _answer(other)

    response = client.get(_url(answer))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert spoken == []


def test_a_speech_failure_reports_a_code(client, student, monkeypatch):
    answer = _answer(student)

    def broken(text, voice):
        raise ModelNotConfigured("nenhum modelo ativo")

    monkeypatch.setattr(listening, "synthesize", broken)

    response = client.get(_url(answer))

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.data["code"] == "provider_unavailable"


def test_listening_requires_authentication(student):
    answer = _answer(student)

    assert APIClient().get(_url(answer)).status_code == status.HTTP_401_UNAUTHORIZED
