import pytest

from apps.agents.services.schemas import RoutingDecision
from apps.catalog.models import Scenario
from apps.voice.tests.round_shapes import STUDENT_TEXT, play_round, speaker

pytestmark = pytest.mark.django_db

_OPENING = "Hello, let's talk about the deadline."
_NOBODY = RoutingDecision(speaker="none", topic_owner="none")


def _expected(*lines: tuple[str, str]) -> list:
    """Os quadros esperados: o nome de quem fala e depois o áudio, para cada fala da rodada."""
    frames: list = []
    for name, text in lines:
        frames.extend([speaker(name), ("audio", text)])
    return frames


def _conversation(opening_name: str, *lines: tuple[str, str]) -> list[str]:
    """A conversa que a tentativa registra: abertura, resposta do aluno e as falas da rodada."""
    spoken = [f"[{opening_name}] {_OPENING}", STUDENT_TEXT]
    spoken.extend(f"[{name}] {text}" for name, text in lines)
    return spoken


_ONE_LINE = [("Rachel", "What have you finished so far?")]
_REDIRECT = [
    ("Rachel", "That one is for Tom."),
    ("Tom", "Sure. What is still missing on the export?"),
]
_HAND_FLOOR = [
    ("Rachel", "I see. Tom will take it from here."),
    ("Tom", "Thanks. What is still missing on the export?"),
]
_DANGLING = [
    ("Rachel", "Tom, what do you think about that delay?"),
    ("Tom", "I think we need the export first. Can you send it today?"),
]


@pytest.mark.parametrize(
    ("slug", "routing", "round_lines"),
    [
        pytest.param("negociar-prazo", _NOBODY, _ONE_LINE, id="one-line"),
        pytest.param(
            "negociar-prazo",
            RoutingDecision(speaker="rachel", topic_owner="tom"),
            _REDIRECT,
            id="student-redirect",
        ),
        pytest.param(
            "entrevista-de-emprego",
            RoutingDecision(speaker="none", topic_owner="tom"),
            _HAND_FLOOR,
            id="topic-takeover",
        ),
        pytest.param("negociar-prazo", _NOBODY, _DANGLING, id="line-addressed-to-the-colleague"),
    ],
)
def test_a_round_reaches_the_student_and_the_attempt_in_the_same_order(
    django_user_model, monkeypatch, slug, routing, round_lines
):
    lines = [_OPENING, *(text for _, text in round_lines)]

    frames, installed = play_round(
        monkeypatch, django_user_model, lines, routing, slug=slug, audio_count=len(round_lines)
    )

    assert frames == _expected(*round_lines)
    assert installed.synthesized == [_OPENING, *(text for _, text in round_lines)]
    assert installed.evaluated == [_conversation("Rachel", *round_lines)]


def test_the_supporting_persona_speaks_first_and_the_persona_of_the_turn_closes(
    django_user_model, monkeypatch
):
    round_lines = [
        ("Mike", "The elevator is loud at night, sir."),
        ("Emma", "I am sorry about that. Which floor would you like?"),
    ]
    lines = [_OPENING, *(text for _, text in round_lines)]

    frames, installed = play_round(
        monkeypatch,
        django_user_model,
        lines,
        RoutingDecision(speaker="mike", topic_owner="none"),
        slug="quarto-novo-barulhento",
        audio_count=2,
    )

    assert frames == _expected(*round_lines)
    assert installed.evaluated == [_conversation("Emma", *round_lines)]


def test_the_persona_called_answers_without_a_question_and_the_supporting_one_closes(
    django_user_model, monkeypatch
):
    Scenario.objects.filter(slug="quarto-novo-barulhento").update(max_turns=4)
    round_lines = [
        ("Emma", "I understand, sir."),
        ("Mike", "Shall I carry your bags to the new room?"),
    ]
    lines = [_OPENING, *(text for _, text in round_lines)]

    frames, installed = play_round(
        monkeypatch,
        django_user_model,
        lines,
        RoutingDecision(speaker="emma", topic_owner="none"),
        slug="quarto-novo-barulhento",
        audio_count=2,
    )

    assert frames == _expected(*round_lines)
    assert installed.evaluated == [_conversation("Emma", *round_lines)]
