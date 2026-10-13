from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from apps.agents.evaluation.output import captured_output
from apps.agents.evaluation.schemas import ROLE_ITEMS, RoleVerdict, SemanticVerdict
from apps.agents.services.scenario_content import Role, ScenarioContent
from apps.agents.services.transcript import transcript_text
from apps.catalog.models import Archetype
from apps.llm.constants import ModelPurpose
from apps.llm.services.factory import get_structured_llm

ATTEMPTS = 2

_ROLE_PROMPT = """You are a strict reviewer of an English-practice role-play. A Brazilian student
talks to fictional characters in a scene. Review ONE line spoken by a character.

SCENE
{context}

WHAT THE STUDENT WANTS
{objective}

THE CHARACTER WHOSE LINE YOU REVIEW
{name}, {scene_function}.
Archetype: {archetype} - {archetype_description}
Traits: {traits}
How the character resists: {resistance}
What makes the character concede: {concession}

THE OTHER CHARACTER(S) IN THE SCENE
{others}

FACTS THE CHARACTER KNOWS (these notes may be written in Portuguese)
{facts}

RULES OF THE LEVEL
- Language: {language}
- Questions: {questions}
- How to reply to the student: {reply_to_student}

HOW A ROUND WORKS
In one round, a character may hand the floor to the other one: the first line is then addressed
to the other character, with no question to the student, and the other character asks the
student. A line that is addressed to the other character is expected in that case.

CONVERSATION BEFORE THE LINE
{history}

THE LINE TO REVIEW
{line}

Answer every item of the checklist. Use na only where the item says so or when it clearly does
not apply to this line. Be strict, and base each answer only on the text above."""

_SEMANTIC_PROMPT = """You are a strict reviewer of an English-practice role-play. A Brazilian
student talks to fictional characters in a scene.

CONVERSATION BEFORE THE ROUND
{history}

THE ROUND UNDER REVIEW
{round_lines}

QUESTION
{question}

Answer yes only if the statement in the question is true for the round above."""


class JudgeFailed(Exception):
    """O juiz não devolveu um veredito utilizável depois das tentativas permitidas."""


def archetype_description(name: str) -> str:
    """A descrição do arquétipo no catálogo: o conteúdo de execução traz só o nome."""
    return Archetype.objects.filter(name=name).values_list("description", flat=True).first() or ""


def _others(content: ScenarioContent, role: Role) -> str:
    others = [
        f"- {other.name}: {other.scene_function}"
        for other in content.roles
        if other.key != role.key
    ]
    return "\n".join(others) or "- nobody"


def _invoke(schema: type, prompt: str) -> Any:
    last: Exception | None = None
    for _ in range(ATTEMPTS):
        try:
            with captured_output():
                return get_structured_llm(ModelPurpose.JUDGE, schema).invoke(
                    [HumanMessage(content=prompt)]
                )
        except Exception as exc:
            last = exc
    raise JudgeFailed(f"{type(last).__name__}: {last}") from last


def judge_line(
    content: ScenarioContent, role: Role, history: list[BaseMessage], line: str
) -> dict[str, dict[str, str]]:
    """Pede ao avaliador o veredito de cada item da lista de verificação sobre uma fala.

    Recebe a conversa até a fala, o cartão do papel (com a descrição do arquétipo, lida do
    catálogo) e as regras do nível. Devolve `{item: {"answer": "yes|no|na", "reason": ...}}`.
    """
    prompt = _ROLE_PROMPT.format(
        context=content.context,
        objective=content.objective,
        name=role.name,
        scene_function=role.scene_function,
        archetype=role.archetype,
        archetype_description=archetype_description(role.archetype),
        traits=role.traits,
        resistance=role.resistance,
        concession=role.concession,
        others=_others(content, role),
        facts=role.extra_instruction.strip() or "(none)",
        language=content.language,
        questions=content.questions,
        reply_to_student=content.reply_to_student,
        history=transcript_text(history) or "(no one has spoken yet)",
        line=line,
    )
    verdict = _invoke(RoleVerdict, prompt)
    return {
        item: {
            "answer": getattr(verdict, item),
            "reason": getattr(verdict, f"{item}_reason", ""),
        }
        for item in ROLE_ITEMS
    }


def judge_question(
    question: str, history: list[BaseMessage], round_lines: list[str]
) -> dict[str, str]:
    """Responde a uma pergunta de sim ou não escrita no caso, sobre as falas de uma rodada."""
    prompt = _SEMANTIC_PROMPT.format(
        history=transcript_text(history) or "(no one has spoken yet)",
        round_lines="\n".join(round_lines),
        question=question,
    )
    verdict = _invoke(SemanticVerdict, prompt)
    return {"answer": verdict.answer, "reason": verdict.reason}


def judge_round(
    content: ScenarioContent, history: list[BaseMessage], round_lines: list[str]
) -> list[dict[str, Any]]:
    """Julga cada fala de persona de uma rodada, com a conversa até aquela fala."""
    key_by_name = {role.name: role for role in content.roles}
    seen = list(history)
    results = []
    for line in round_lines:
        speaker = line[1 : line.index("]")] if line.startswith("[") and "]" in line else ""
        role = key_by_name.get(speaker)
        if role is not None:
            try:
                results.append(
                    {"line": line, "items": judge_line(content, role, seen, line), "error": ""}
                )
            except JudgeFailed as exc:
                results.append({"line": line, "items": {}, "error": str(exc)})
        seen.append(AIMessage(content=line))
    return results
