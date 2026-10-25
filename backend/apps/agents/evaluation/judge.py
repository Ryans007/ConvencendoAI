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
CONTEXT_LINES = 4

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
Presence in the scene: {presence}

THE OTHER CHARACTER(S) IN THE SCENE
{others}

FACTS THE CHARACTER KNOWS (these notes may be written in Portuguese)
{facts}

RULES OF THE LEVEL
- Language: {language}
- Questions: {questions}
- How to reply to the student: {reply_to_student}

HOW A ROUND WORKS
In one round, a character may hand the floor to another one: the first line is then addressed
to that character, with no question to the student, and that character asks the student. A
line that is addressed to another character is expected in that case. A supporting character
never leads the scene: when it speaks first in a round, its line is brief and has no question,
and a principal character asks the student right after; when it closes the round, it ends with
one short question about its part of the scene.
{round_note}{closing_note}
CONVERSATION BEFORE THE LINE
{history}

THE LINE TO REVIEW
{line}

Answer every item of the checklist. Use na only where the item says so or when it clearly does
not apply to this line. Be strict, and base each answer only on the text above."""

_CLOSING_NOTE = """
THIS IS THE FINAL LINE OF THE SCENE
The session ends right after this line, so a closing line is expected: it contains NO question to
the student and no longer challenges or resists. Do not penalise it for not asking or for not
resisting, and use na for the items about asking or resisting. Judge instead whether the closing
fits the character's function and archetype (for example, a supporter backs the student up and
does not announce decisions that belong to someone else), and apply the other items normally.
"""

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


_PRINCIPAL = "principal character: leads the conversation with the student"
_SUPPORTING = "supporting character: joins only briefly and never leads the scene"
_FOLLOWED_NOTE = """
THIS LINE DOES NOT CLOSE THE ROUND
Another character speaks right after this line, in the same round, and asks the student.
"""


def _others(content: ScenarioContent, role: Role) -> str:
    others = [
        f"- {other.name}: {other.scene_function}"
        + (" (supporting character)" if other.supporting else "")
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


def context_lines(history: list[BaseMessage], limit: int | None = CONTEXT_LINES) -> list[str]:
    """As últimas `limit` falas da conversa (todas, sem limite), uma por linha."""
    lines = transcript_text(history).splitlines()
    return lines if limit is None else lines[-limit:]


def judge_line(
    content: ScenarioContent,
    role: Role,
    history: list[BaseMessage],
    line: str,
    final: bool = False,
    closes_round: bool = True,
) -> dict[str, dict[str, str]]:
    """Pede ao avaliador o veredito de cada item da lista de verificação sobre uma fala.

    Recebe a conversa até a fala, o cartão do papel (com a descrição do arquétipo, lida do
    catálogo) e as regras do nível. Quando a fala é a última da cena (`final`), o prompt avisa
    que ela é um fechamento: sem pergunta e sem resistência, que o sistema manda e o juiz não
    pode cobrar. Quando outra fala vem depois dela na mesma rodada (`closes_round` falso), o
    juiz é avisado de que uma fala sem pergunta ao aluno é esperada ali. Devolve
    `{item: {"answer": "yes|no|na", "reason": ...}}`.
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
        presence=_SUPPORTING if role.supporting else _PRINCIPAL,
        others=_others(content, role),
        facts=role.extra_instruction.strip() or "(none)",
        language=content.language,
        questions=content.questions,
        reply_to_student=content.reply_to_student,
        round_note="" if closes_round else _FOLLOWED_NOTE,
        closing_note=_CLOSING_NOTE if final else "",
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


def judged_entry(
    content: ScenarioContent,
    role: Role,
    history: list[BaseMessage],
    line: str,
    final: bool = False,
    closes_round: bool = True,
) -> dict[str, Any]:
    """O julgamento de uma fala, com a fala, as últimas falas anteriores e se era a final.

    O contexto fica guardado junto do veredito para quem revisa o juiz ver o que ele viu: os
    itens "responde ao aluno primeiro", "não repete pergunta" e "só usa fatos da cena" só se
    decidem com o que veio antes. Uma falha do juiz fica registrada na entrada, sem interromper.
    """
    entry: dict[str, Any] = {
        "line": line,
        "context": context_lines(history),
        "final": final,
        "items": {},
        "error": "",
    }
    try:
        entry["items"] = judge_line(content, role, history, line, final, closes_round)
    except JudgeFailed as exc:
        entry["error"] = str(exc)
    return entry


def judge_round(
    content: ScenarioContent, history: list[BaseMessage], round_lines: list[str]
) -> list[dict[str, Any]]:
    """Julga cada fala de persona de uma rodada, com a conversa até aquela fala."""
    key_by_name = {role.name: role for role in content.roles}
    seen = list(history)
    results = []
    for index, line in enumerate(round_lines):
        speaker = line[1 : line.index("]")] if line.startswith("[") and "]" in line else ""
        role = key_by_name.get(speaker)
        if role is not None:
            closes = index == len(round_lines) - 1
            results.append(judged_entry(content, role, seen, line, closes_round=closes))
        seen.append(AIMessage(content=line))
    return results
