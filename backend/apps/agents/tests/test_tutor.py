import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.services import tutor
from apps.agents.services.scenario_content import load_scenario_content
from apps.agents.services.schemas import SuggestedAnswer
from apps.catalog.models import Level, Scenario

pytestmark = pytest.mark.django_db

_HISTORY = [
    AIMessage(content="[Rachel] Tell me about a project you worked on."),
    HumanMessage(content="I worked on a web app for online orders."),
    AIMessage(content="[Tom] What technical decision did you make in that project, and why?"),
]


class _Recorder:
    def __init__(self, *texts: str):
        self.prompts = []
        self._texts = iter(texts)

    def invoke(self, messages):
        self.prompts.append(messages[0].content)
        return SuggestedAnswer(text=next(self._texts))


def _content(level_order: int):
    return load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=level_order)
    )


def _suggest(monkeypatch, level_order: int, *texts: str):
    recorder = _Recorder(*texts)
    monkeypatch.setattr(tutor, "get_structured_llm", lambda purpose, schema: recorder)
    answer = tutor.suggest_answer(_content(level_order), _HISTORY)
    return answer, recorder


def test_the_prompt_carries_the_conversation_and_the_question_to_answer(monkeypatch):
    _, recorder = _suggest(monkeypatch, 3, "Escolhi PostgreSQL porque os dados tinham relações.")

    prompt = recorder.prompts[0]
    assert "[Tom] What technical decision did you make in that project, and why?" in prompt
    assert "Student: I worked on a web app for online orders." in prompt
    assert "Answer the character's LAST line" in prompt


def test_the_prompt_carries_the_level_format_and_the_criteria_privately(monkeypatch):
    content = _content(3)
    _, recorder = _suggest(monkeypatch, 3, "Sugestão.")

    prompt = recorder.prompts[0]
    assert content.expected_production in prompt
    for criterion in content.criteria:
        assert criterion.text in prompt
    assert "never mention it to the student" in prompt
    assert "Never mention criteria, evaluation, score, passing" in prompt


def test_the_prompt_forbids_english_and_asks_for_first_person(monkeypatch):
    _, recorder = _suggest(monkeypatch, 1, "Sim, trabalhei em equipe.")

    prompt = recorder.prompts[0]
    assert "Portuguese only. No English words or sentences" in prompt
    assert "First person, as the student" in prompt
    assert "Stay consistent with everything the student already said" in prompt


def test_each_level_brings_its_own_format(monkeypatch):
    _, level_one = _suggest(monkeypatch, 1, "Sim.")
    _, level_three = _suggest(monkeypatch, 3, "Sugestão.")

    assert _content(1).expected_production in level_one.prompts[0]
    assert _content(3).expected_production in level_three.prompts[0]
    assert _content(3).expected_production not in level_one.prompts[0]


def test_returns_the_suggestion_without_surrounding_spaces(monkeypatch):
    answer, _ = _suggest(monkeypatch, 3, "  Escolhi PostgreSQL.  ")

    assert answer == "Escolhi PostgreSQL."


def test_an_empty_suggestion_is_retried_once(monkeypatch):
    answer, recorder = _suggest(monkeypatch, 3, "", "Escolhi PostgreSQL.")

    assert answer == "Escolhi PostgreSQL."
    assert len(recorder.prompts) == 2


def test_two_empty_suggestions_give_an_empty_answer(monkeypatch):
    answer, recorder = _suggest(monkeypatch, 3, "", "   ")

    assert answer == ""
    assert len(recorder.prompts) == 2


def test_a_suggestion_in_english_is_discarded_and_retried(monkeypatch):
    answer, recorder = _suggest(
        monkeypatch,
        3,
        "I found the new API needs extra data mapping, which will take three days.",
        "Descobri que a nova API precisa de mais trabalho, e isso vai levar três dias.",
    )

    assert answer.startswith("Descobri que a nova API")
    assert len(recorder.prompts) == 2


def test_two_suggestions_in_english_give_an_empty_answer(monkeypatch):
    answer, _ = _suggest(monkeypatch, 3, "Yes, I did.", "We used the API for that.")

    assert answer == ""


def test_portuguese_full_of_technology_names_is_still_portuguese():
    assert not tutor.looks_english("Decidi usar FastAPI com PostgreSQL e Redis porque era mais rápido.")
    assert not tutor.looks_english("Sim, trabalhei em equipe.")
    assert not tutor.looks_english("aplicativo web")
    assert tutor.looks_english("I found the new API needs extra data mapping.")
    assert tutor.looks_english("Could we push the deadline by a week?")
