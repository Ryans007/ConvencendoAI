from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.agents.services.schemas import ReviewVerdict
from apps.catalog.models import Level, Scenario
from apps.llm.models import LLMModel, LLMProvider
from apps.progress.models import Attempt
from apps.review.models import ReviewAnswer, ReviewItem, ReviewOccurrence
from apps.review.services import answering, listening
from apps.usage.constants import UsagePurpose
from apps.usage.models import AccessLimits, ModelUsage
from apps.usage.services.review_limits import review_limit_reached

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture
def student(django_user_model):
    return django_user_model.objects.create_user(username="aluno", password="Xk9#mQ2vLp8Z")


@pytest.fixture
def client(student):
    api_client = APIClient()
    api_client.force_authenticate(user=student)
    return api_client


@pytest.fixture
def item(student) -> ReviewItem:
    review_item = ReviewItem.objects.create(
        user=student, rule="regra", box=0, due_on=TODAY
    )
    attempt = Attempt.objects.create(
        user=student,
        scenario=Scenario.objects.get(slug="entrevista-de-emprego"),
        level=Level.objects.get(order=3),
    )
    ReviewOccurrence.objects.create(
        item=review_item, attempt=attempt, produced="x", correct="I worked there."
    )
    return review_item


@pytest.fixture
def llm():
    provider = LLMProvider.objects.create(code="g", name="G", base_url="https://x/v1", api_key="test-key")
    return LLMModel.objects.create(provider=provider, model_id="m", display_name="m")


def _calls(user, item, llm, count: int, seconds_ago: int = 0) -> None:
    for _ in range(count):
        row = ModelUsage.objects.create(
            user=user,
            username_at_time=user.username,
            review_item=item,
            purpose=UsagePurpose.JUDGE,
            llm_model=llm,
            model_id_at_time=llm.model_id,
            cost_usd=Decimal(0),
        )
        if seconds_ago:
            ModelUsage.objects.filter(pk=row.pk).update(
                created_at=timezone.now() - timedelta(seconds=seconds_ago)
            )


def _send(client, item):
    audio = SimpleUploadedFile("a.webm", b"x" * 64, content_type="audio/webm")
    return client.post(
        f"/api/review/items/{item.pk}/answers/", {"audio": audio}, format="multipart"
    )


def test_an_answer_over_the_limit_is_refused_without_transcribing_judging_or_spending(
    client, student, item, llm, monkeypatch
):
    _calls(student, item, llm, 20)

    def must_not_run(*args, **kwargs):
        raise AssertionError("nenhum modelo pode ser chamado")

    monkeypatch.setattr(answering, "transcribe", must_not_run)
    monkeypatch.setattr(answering, "judge_review_answer", must_not_run)

    response = _send(client, item)

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.data["code"] == "too_many_requests"
    assert response["Retry-After"] == "60"
    assert not ReviewAnswer.objects.filter(item=item).exists()


def test_an_answer_below_the_limit_goes_through(client, student, item, llm, monkeypatch):
    _calls(student, item, llm, 19)
    monkeypatch.setattr(answering, "transcribe", lambda audio: "I worked there")
    monkeypatch.setattr(
        answering,
        "judge_review_answer",
        lambda **kwargs: ReviewVerdict(correct=True, feedback="Certo."),
    )

    assert _send(client, item).status_code == status.HTTP_200_OK


def test_the_limit_frees_after_a_minute(client, student, item, llm, monkeypatch):
    _calls(student, item, llm, 20, seconds_ago=61)
    monkeypatch.setattr(answering, "transcribe", lambda audio: "I worked there")
    monkeypatch.setattr(
        answering,
        "judge_review_answer",
        lambda **kwargs: ReviewVerdict(correct=True, feedback="Certo."),
    )

    assert _send(client, item).status_code == status.HTTP_200_OK


def test_the_calls_of_another_student_do_not_count(client, student, item, llm, django_user_model):
    other = django_user_model.objects.create_user(username="outro", password="Xk9#mQ2vLp8Z")
    other_item = ReviewItem.objects.create(user=other, rule="r", box=0, due_on=TODAY)
    _calls(other, other_item, llm, 50)

    assert review_limit_reached(student) is False


def test_calls_outside_the_review_do_not_count(student, llm):
    for _ in range(30):
        ModelUsage.objects.create(
            user=student,
            username_at_time=student.username,
            purpose=UsagePurpose.PERSONA,
            llm_model=llm,
            model_id_at_time=llm.model_id,
            cost_usd=Decimal(0),
        )

    assert review_limit_reached(student) is False


def test_the_limit_follows_the_configuration(student, item, llm):
    limits = AccessLimits.get_solo()
    limits.max_review_calls_per_minute = 3
    limits.save()
    _calls(student, item, llm, 3)

    assert review_limit_reached(student) is True


def test_the_correct_form_audio_is_limited_too_without_calling_the_model(
    client, student, item, llm, monkeypatch
):
    answer = ReviewAnswer.objects.create(
        item=item, step=1, attempt=1, heard="x", correct=True, feedback="f",
        revealed_correct="I worked there.",
    )
    _calls(student, item, llm, 20)

    def must_not_run(*args, **kwargs):
        raise AssertionError("o áudio não pode ser sintetizado")

    monkeypatch.setattr(listening, "synthesize", must_not_run)

    response = client.get(f"/api/review/answers/{answer.pk}/audio/")

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.data["code"] == "too_many_requests"


def test_an_answer_of_another_student_is_still_not_found_even_over_the_limit(
    client, student, llm, django_user_model
):
    other = django_user_model.objects.create_user(username="outro", password="Xk9#mQ2vLp8Z")
    other_item = ReviewItem.objects.create(user=other, rule="r", box=0, due_on=TODAY)
    _calls(student, other_item, llm, 20)

    assert _send(client, other_item).status_code == status.HTTP_404_NOT_FOUND
