from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.agents.services.review_teacher import ReviewJudgmentFailed
from apps.agents.services.schemas import ReviewVerdict
from apps.catalog.models import Level, Scenario
from apps.llm.services.factory import ModelNotConfigured
from apps.progress.models import Attempt
from apps.review.models import ReviewAnswer, ReviewItem, ReviewOccurrence, ReviewResultKind
from apps.review.services import answering

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
CORRECT_FORM = "I worked there yesterday."
CORRECTION = "Last week I finished the project."
HIT = ReviewVerdict(correct=True, feedback="Certo, o tempo já terminou.")
MISS = ReviewVerdict(
    correct=False, feedback="Repare em yesterday: ele marca um tempo que já terminou.",
    correction=CORRECTION,
)


@pytest.fixture
def student(django_user_model):
    return django_user_model.objects.create_user(username="aluno", password="Xk9#mQ2vLp8Z")


@pytest.fixture
def client(student):
    api_client = APIClient()
    api_client.force_authenticate(user=student)
    return api_client


class _Teacher:
    def __init__(self):
        self.verdicts: list = []
        self.calls: list[dict] = []
        self.on_call = None

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.on_call:
            self.on_call()
        verdict = self.verdicts.pop(0)
        if isinstance(verdict, Exception):
            raise verdict
        return verdict


@pytest.fixture
def teacher(monkeypatch):
    fake = _Teacher()
    monkeypatch.setattr(answering, "judge_review_answer", fake)
    monkeypatch.setattr(answering, "transcribe", lambda audio: "I worked there yesterday")
    return fake


def _item(user, *, box: int = 1, archived: bool = False, due_in_days: int = 0) -> ReviewItem:
    item = ReviewItem.objects.create(
        user=user,
        rule="past simple with a finished time expression",
        box=box,
        due_on=TODAY + timedelta(days=due_in_days),
        archived_at=timezone.now() if archived else None,
    )
    attempt = Attempt.objects.create(
        user=user,
        scenario=Scenario.objects.get(slug="entrevista-de-emprego"),
        level=Level.objects.get(order=3),
    )
    ReviewOccurrence.objects.create(
        item=item, attempt=attempt, produced="I have worked there yesterday", correct=CORRECT_FORM
    )
    return item


def _audio(content_type: str = "audio/webm", size: int = 64) -> SimpleUploadedFile:
    return SimpleUploadedFile("audio.webm", b"x" * size, content_type=content_type)


def _send(client, item: ReviewItem, audio=None):
    return client.post(
        f"/api/review/items/{item.pk}/answers/",
        {"audio": audio or _audio()},
        format="multipart",
    )


def test_a_correct_first_answer_moves_to_step_two_and_shows_the_correct_form(
    client, student, teacher
):
    item = _item(student)
    teacher.verdicts = [HIT]

    response = _send(client, item)

    assert response.status_code == status.HTTP_200_OK
    data = response.data
    assert data["status"] == "judged"
    assert (data["correct"], data["heard"]) == (True, "I worked there yesterday")
    assert data["feedback"] == HIT.feedback
    assert data["revealed_correct"] == CORRECT_FORM
    assert data["next"] == {"step": 2, "attempt": 1}
    assert data["result"] is None
    assert item.answers.count() == 1


def test_the_server_decides_the_step_and_the_attempt_for_the_teacher(client, student, teacher):
    item = _item(student)
    teacher.verdicts = [MISS, HIT]

    _send(client, item)
    _send(client, item)

    assert [(call["step"], call["attempt"]) for call in teacher.calls] == [(1, 1), (1, 2)]
    assert teacher.calls[0]["correct"] == CORRECT_FORM
    assert teacher.calls[0]["said"] == "I have worked there yesterday"


def test_a_first_miss_gives_a_hint_without_the_correct_form(client, student, teacher):
    item = _item(student)
    teacher.verdicts = [MISS]

    data = _send(client, item).data

    assert data["correct"] is False
    assert data["revealed_correct"] == ""
    assert data["next"] == {"step": 1, "attempt": 2}
    answer = item.answers.get()
    assert answer.correction == CORRECTION
    assert answer.revealed_correct == ""


def test_two_misses_in_step_one_reveal_the_form_and_move_on(client, student, teacher):
    item = _item(student)
    teacher.verdicts = [MISS, MISS]

    _send(client, item)
    data = _send(client, item).data

    assert data["revealed_correct"] == CORRECT_FORM
    assert data["next"] == {"step": 2, "attempt": 1}


def test_both_steps_on_the_first_try_raise_the_box_and_set_the_new_due_date(
    client, student, teacher
):
    item = _item(student, box=1)
    teacher.verdicts = [HIT, HIT]

    _send(client, item)
    data = _send(client, item).data

    assert data["next"] is None
    assert data["result"] == {
        "outcome": "first_try",
        "interval_days": 7,
        "due_on": (TODAY + timedelta(days=7)).isoformat(),
        "mastered": False,
    }
    item.refresh_from_db()
    assert (item.box, item.due_on) == (2, TODAY + timedelta(days=7))
    result = item.results.get()
    assert (result.outcome, result.box_before, result.box_after) == (
        ReviewResultKind.FIRST_TRY, 1, 2,
    )
    assert set(item.answers.values_list("result_id", flat=True)) == {result.pk}


def test_a_second_attempt_in_step_two_keeps_the_box(client, student, teacher):
    item = _item(student, box=1)
    teacher.verdicts = [HIT, MISS, HIT]

    for _ in range(3):
        data = _send(client, item).data

    assert data["result"]["outcome"] == "second_try"
    item.refresh_from_db()
    assert (item.box, item.due_on) == (1, TODAY + timedelta(days=3))


def test_a_step_without_a_hit_sends_the_item_back_to_the_first_box(client, student, teacher):
    item = _item(student, box=3)
    teacher.verdicts = [MISS, MISS, HIT]

    for _ in range(3):
        data = _send(client, item).data

    assert data["result"]["outcome"] == "failed"
    assert data["result"]["interval_days"] == 1
    item.refresh_from_db()
    assert (item.box, item.due_on) == (0, TODAY + timedelta(days=1))


def test_step_two_ending_in_a_miss_reveals_the_teacher_correction(client, student, teacher):
    item = _item(student)
    teacher.verdicts = [HIT, MISS, MISS]

    for _ in range(3):
        data = _send(client, item).data

    assert data["revealed_correct"] == CORRECTION
    assert data["result"]["outcome"] == "failed"


def test_a_mastered_result_is_flagged(client, student, teacher):
    item = _item(student, box=4)
    teacher.verdicts = [HIT, HIT]

    _send(client, item)
    data = _send(client, item).data

    assert data["result"]["mastered"] is True
    assert data["result"]["interval_days"] == 60


def test_the_finished_item_leaves_the_round(client, student, teacher):
    item = _item(student)
    teacher.verdicts = [HIT, HIT]

    _send(client, item)
    _send(client, item)

    assert client.get("/api/review/round/").data["count"] == 0


def test_silence_is_not_heard_and_saves_nothing(client, student, teacher, monkeypatch):
    item = _item(student)
    monkeypatch.setattr(answering, "transcribe", lambda audio: "   ")

    response = _send(client, item)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "not_heard"
    assert response.data["next"] is None and response.data["result"] is None
    assert teacher.calls == []
    assert item.answers.count() == 0


def test_a_transcription_failure_saves_nothing_and_reports_a_code(
    client, student, teacher, monkeypatch
):
    item = _item(student)

    def broken(audio):
        raise ModelNotConfigured("nenhum modelo ativo")

    monkeypatch.setattr(answering, "transcribe", broken)

    response = _send(client, item)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.data["code"] == "provider_unavailable"
    assert item.answers.count() == 0


def test_a_teacher_failure_saves_nothing_and_keeps_the_attempt(client, student, teacher):
    item = _item(student)
    teacher.verdicts = [ReviewJudgmentFailed("vazio"), HIT]

    failed = _send(client, item)
    retried = _send(client, item)

    assert failed.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert failed.data["code"] == "provider_unavailable"
    assert retried.data["next"] == {"step": 2, "attempt": 1}
    assert [(call["step"], call["attempt"]) for call in teacher.calls] == [(1, 1), (1, 1)]


def test_an_unexpected_failure_reports_the_unexpected_code(client, student, teacher):
    item = _item(student)
    teacher.verdicts = [RuntimeError("boom")]

    response = _send(client, item)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.data["code"] == "unexpected"


def test_a_duplicate_send_that_lost_the_race_is_a_conflict(client, student, teacher):
    item = _item(student)
    teacher.verdicts = [HIT]

    def another_send_finished_first():
        ReviewAnswer.objects.create(
            item=item, step=1, attempt=1, heard="x", correct=True, feedback="ok"
        )

    teacher.on_call = another_send_finished_first

    response = _send(client, item)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert item.answers.count() == 1


def test_a_missing_audio_is_refused(client, student, teacher):
    item = _item(student)

    response = client.post(f"/api/review/items/{item.pk}/answers/", {}, format="multipart")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert teacher.calls == []


def test_an_audio_over_the_limit_is_refused(client, student, teacher):
    item = _item(student)

    response = _send(client, item, _audio(size=2 * 1024 * 1024 + 1))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "grande demais" in str(response.data["audio"])


def test_an_unsupported_audio_type_is_refused(client, student, teacher):
    item = _item(student)

    response = _send(client, item, _audio(content_type="text/plain"))

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_the_codecs_parameter_does_not_make_a_type_unsupported(client, student, teacher):
    item = _item(student)
    teacher.verdicts = [HIT]

    response = _send(client, item, _audio(content_type="audio/webm;codecs=opus"))

    assert response.status_code == status.HTTP_200_OK


def test_an_item_that_is_not_the_students_archived_or_not_due_is_not_found(
    client, student, teacher, django_user_model
):
    other = django_user_model.objects.create_user(username="outro", password="Xk9#mQ2vLp8Z")
    items = [
        _item(other),
        _item(student, archived=True),
        _item(student, due_in_days=2),
    ]

    codes = [_send(client, item).status_code for item in items]

    assert codes == [status.HTTP_404_NOT_FOUND] * 3
    assert teacher.calls == []


def test_answering_requires_authentication(student):
    item = _item(student)

    response = APIClient().post(
        f"/api/review/items/{item.pk}/answers/", {"audio": _audio()}, format="multipart"
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
