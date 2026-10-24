import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt, ScoreBreakdown, SpeechTurn
from apps.review.models import ReviewItem, ReviewOccurrence
from apps.review.services import listening

pytestmark = pytest.mark.django_db

_PASSWORD = "Xk9#mQ2vLp8Z"
_LONG_TEXT = (
    "I booked a quiet room near the elevator but the shower is broken and the water is cold. "
    "Could you send someone this afternoon or move me to another floor before dinner tonight? "
    "My meeting starts early tomorrow so I really need to rest properly."
)


def _student(django_user_model, username: str = "aluno"):
    return django_user_model.objects.create_user(username=username, password=_PASSWORD)


def _attempt(user, *, level_order: int = 3, completed: bool = True) -> Attempt:
    return Attempt.objects.create(
        user=user,
        scenario=Scenario.objects.get(slug="negociar-prazo"),
        level=Level.objects.get(order=level_order),
        final_score=80,
        passed=True,
        feedback="Você explicou bem o atraso.",
        completed_at=timezone.now() if completed else None,
    )


def _occurrence(attempt: Attempt, *, archived: bool = False, **fields) -> ReviewOccurrence:
    item = ReviewItem.objects.create(
        user=attempt.user,
        rule="past simple with a finished time expression",
        box=1,
        due_on=timezone.localdate(),
        archived_at=timezone.now() if archived else None,
    )
    values = {
        "produced": "I have finished it last week",
        "correct": "I finished it last week",
        "note": "Repare no tempo que já terminou.",
    }
    values.update(fields)
    return ReviewOccurrence.objects.create(item=item, attempt=attempt, **values)


def _speech_turn(attempt: Attempt, order: int, **fields) -> SpeechTurn:
    values = {
        "waited_ms": 3500,
        "leading_silence_ms": 500,
        "speech_ms": 30000,
        "word_count": 45,
        "long_pauses": 1,
        "after_hint": False,
        "text": _LONG_TEXT,
    }
    values.update(fields)
    return SpeechTurn.objects.create(attempt=attempt, order=order, **values)


def _get(user, path: str):
    client = APIClient()
    client.force_authenticate(user=user)
    return client.get(path)


def test_the_report_carries_comments_mistakes_measures_and_the_scoring(django_user_model):
    user = _student(django_user_model)
    attempt = _attempt(user)
    ScoreBreakdown.objects.create(
        attempt=attempt,
        dimension="fluency",
        value=11,
        weight_at_time=15,
        comment="Você levou cerca de 4 segundos para começar.",
    )
    occurrence = _occurrence(
        attempt,
        explanation="Com um tempo que já terminou, use o passado simples.",
        examples=["I called her last night.", "We met on Monday."],
    )
    _speech_turn(attempt, 1)
    _speech_turn(attempt, 2)

    data = _get(user, f"/api/attempts/{attempt.pk}/").data

    assert data["score_breakdowns"][0]["comment"] == "Você levou cerca de 4 segundos para começar."
    assert data["mistakes"] == [
        {
            "id": occurrence.pk,
            "produced": "I have finished it last week",
            "correct": "I finished it last week",
            "explanation": "Com um tempo que já terminou, use o passado simples.",
            "examples": ["I called her last night.", "We met on Monday."],
        }
    ]
    metrics = data["speech_metrics"]
    assert metrics["reaction_seconds"] == 4.0
    assert metrics["words_per_minute"] == 90
    assert metrics["lexical_diversity"] is not None
    assert metrics["lexical_range"] is not None
    assert data["scoring"]["passing_score"] == 70
    assert data["scoring"]["fluency"]["measured_share"] == 0.7
    assert data["scoring"]["vocabulary"]["judged_share"] == 0.5


def test_a_level_one_report_shows_only_the_reaction(django_user_model):
    user = _student(django_user_model)
    attempt = _attempt(user, level_order=1)
    _speech_turn(attempt, 1)
    _speech_turn(attempt, 2)

    data = _get(user, f"/api/attempts/{attempt.pk}/").data

    assert data["speech_metrics"]["reaction_seconds"] == 4.0
    assert data["speech_metrics"]["words_per_minute"] is None
    assert data["speech_metrics"]["long_pauses_per_100_words"] is None
    assert data["speech_metrics"]["lexical_diversity"] is None
    assert data["scoring"]["fluency"]["reaction_share"] == 1.0
    assert data["scoring"]["vocabulary"] is None


def test_an_old_attempt_comes_with_the_new_fields_empty(django_user_model):
    user = _student(django_user_model)
    attempt = _attempt(user)
    ScoreBreakdown.objects.create(attempt=attempt, dimension="grammar", value=10, weight_at_time=15)
    _occurrence(attempt)

    data = _get(user, f"/api/attempts/{attempt.pk}/").data

    assert data["score_breakdowns"][0]["comment"] == ""
    assert data["mistakes"][0]["explanation"] == ""
    assert data["mistakes"][0]["examples"] == []
    assert data["speech_metrics"] is None
    assert data["scoring"] == {"passing_score": 70, "fluency": None, "vocabulary": None}


def test_a_mistake_the_student_archived_stays_out_of_the_report(django_user_model):
    user = _student(django_user_model)
    attempt = _attempt(user)
    kept = _occurrence(attempt)
    _occurrence(attempt, archived=True)

    data = _get(user, f"/api/attempts/{attempt.pk}/").data

    assert [mistake["id"] for mistake in data["mistakes"]] == [kept.pk]


def test_the_correct_form_of_an_own_mistake_can_be_heard(django_user_model, monkeypatch):
    user = _student(django_user_model)
    attempt = _attempt(user)
    occurrence = _occurrence(attempt)
    spoken = []

    def fake_synthesize(text, voice):
        spoken.append(text)
        return b"wav-bytes"

    monkeypatch.setattr(listening, "synthesize", fake_synthesize)

    response = _get(user, f"/api/attempts/{attempt.pk}/mistakes/{occurrence.pk}/audio/")

    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"] == "audio/wav"
    assert response.content == b"wav-bytes"
    assert spoken == ["I finished it last week"]


def test_the_audio_of_another_students_mistake_is_not_found(django_user_model, monkeypatch):
    owner = _student(django_user_model, "dono")
    other = _student(django_user_model, "outro")
    attempt = _attempt(owner)
    occurrence = _occurrence(attempt)
    monkeypatch.setattr(listening, "synthesize", lambda text, voice: b"wav-bytes")

    response = _get(other, f"/api/attempts/{attempt.pk}/mistakes/{occurrence.pk}/audio/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_the_audio_of_an_attempt_in_progress_is_not_found(django_user_model, monkeypatch):
    user = _student(django_user_model)
    attempt = _attempt(user, completed=False)
    occurrence = _occurrence(attempt)
    monkeypatch.setattr(listening, "synthesize", lambda text, voice: b"wav-bytes")

    response = _get(user, f"/api/attempts/{attempt.pk}/mistakes/{occurrence.pk}/audio/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_a_provider_failure_answers_service_unavailable(django_user_model, monkeypatch):
    user = _student(django_user_model)
    attempt = _attempt(user)
    occurrence = _occurrence(attempt)

    def failing(text, voice):
        raise RuntimeError("provider down")

    monkeypatch.setattr(listening, "synthesize", failing)

    response = _get(user, f"/api/attempts/{attempt.pk}/mistakes/{occurrence.pk}/audio/")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
