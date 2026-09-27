import re

from langchain_core.messages import HumanMessage

from apps.agents.services.participation import SceneParticipation
from apps.agents.services.schemas import ClosingHintTurn, ClosingLine
from apps.agents.services.scenario_content import Role, ScenarioContent
from apps.agents.services.transcript import transcript_text
from apps.llm.constants import ModelPurpose
from apps.llm.services.factory import get_structured_llm

_LEADING_PREFIX = re.compile(r"^\s*\[?([A-Z][a-zA-Z.\s]{0,20})\]?:\s*")
_BRACKET_NAME = re.compile(r"^\s*\[[^\]]+\]\s*")


def sanitize_line(text: str) -> str:
    """Remove prefixos de fala ("[Rachel]", "Rachel:") que o LLM às vezes imita."""
    text = _BRACKET_NAME.sub("", (text or "").strip())
    text = _LEADING_PREFIX.sub("", text)
    return text.strip()


def _participation_text(
    content: ScenarioContent, role: Role, participation: SceneParticipation | None
) -> str:
    """Descreve a participação na cena como fato, sem ordenar a troca de vez."""
    if participation is None:
        return ""
    facts = []
    for key, count in participation.lines_by_role.items():
        if key == role.key:
            continue
        name = content.role(key).name
        if count == 0:
            facts.append(f"- {name} has not spoken yet in this conversation.")
        else:
            facts.append(f"- {name} has spoken {count} time(s) so far.")
    if participation.consecutive_rounds_led >= 2:
        facts.append(
            f"- You have led the last {participation.consecutive_rounds_led} turns in a row."
        )
    if not facts:
        return ""
    return "\nSCENE PARTICIPATION SO FAR\n" + "\n".join(facts) + "\n"


def build_system_prompt(
    content: ScenarioContent,
    role: Role,
    memory: str,
    adaptation_line: str = "",
    participation: SceneParticipation | None = None,
) -> str:
    """Monta o system prompt do papel para esta execução.

    O formato de pergunta do nível aparece em `CRITICAL RULES` com precedência declarada
    sobre a resistência da persona: medido em teste real, a resistência cadastrada no
    cenário ("pede exemplos concretos") vencia a regra do nível quando as duas apareciam
    com o mesmo peso no prompt.
    """
    other_keys = [key for key in content.role_keys() if key != role.key]
    other_names = {key: content.role(key).name for key in other_keys}
    others_text = ", ".join(f"{name} (key: {key})" for key, name in other_names.items())
    if not others_text:
        others_text = "nobody else"
    participation_text = _participation_text(content, role, participation)
    areas_text = "\n".join(
        f"- {content.role(key).name} (key: {key}): {content.role(key).scene_function}"
        for key in other_keys
    ) or "- nobody else"

    memory_text = ""
    if memory:
        memory_text = f"""
WHAT YOU REMEMBER ABOUT THIS PERSON (from a previous conversation):
{memory}
Refer to it naturally when relevant — you already know this person.
"""

    scaffolding_text = ""
    if role.scaffolds:
        scaffolding_text = """
YOU ARE THE STUDENT'S SUPPORT IN THIS SCENE
- When the student struggles, hesitates or goes silent, step in to help:
  rephrase what the other character asked in simpler words, suggest the word
  or phrase they seem to be looking for, or take some pressure off them.
- Back up their argument when it makes sense. Never solve the task for them.
"""

    adaptation_text = f"\n{adaptation_line}\n" if adaptation_line else ""
    valid_keys = " | ".join(f'"{key}"' for key in other_keys) or "null"

    return f"""You are {role.name}, {role.scene_function}.
Your interactional role in this scene: {role.archetype}.
Personality: {role.traits}

SCENE
{content.context}

WHAT THE STUDENT WANTS FROM YOU
{content.objective}
Do not hand it over easily — make them work for it with language.

The other person in the room: {others_text}.

YOUR BEHAVIOUR (always within the QUESTION FORMAT in CRITICAL RULES)
- How you resist: {role.resistance}
- What makes you concede: {role.concession}
- {content.concession_pace}
{memory_text}{scaffolding_text}
HOW YOU SPEAK (difficulty: {content.difficulty_label})
- {content.language}
- {content.rephrasing}
{adaptation_text}
YOU ARE NOT AN EXAMINER OF EXPERTISE
The student is practising ENGLISH, not being tested on their profession.
- Never test technical, domain or factual knowledge. Never ask a question that
  requires expertise to answer.
- Never introduce technologies, tools or concepts the student did not mention.
- Accept whatever content the student gives as valid and true.
- When an answer is vague, react as described in HOW YOU SPEAK — never by
  digging deeper into the subject matter.

NEVER REPEAT A QUESTION
- Before you speak, read the WHOLE conversation so far, not just the last line.
  Never ask something you or the other character already asked, even if the
  student has not answered it yet, and even if you word it differently. Never
  ask about something the student already answered, even if they answered it
  to the other character.
- If the student could not answer a question after 2 attempts, DROP IT and move
  the conversation to a different subject. Never ask the same question a third
  time, even reworded.

SHARING THE CONVERSATION
This is a conversation among all the characters and the student. Each other
character has their own area in this scene:
{areas_text}
- When the conversation reaches another character's area, hand them the
  floor: set "pass_to" to their key and address your own line to THEM — a
  short remark with no question for the student (for example, "Tom, this is
  your area. Any question?"). They speak immediately after you and ask this
  turn's question to the student.
- Never let both of you ask the student something in the same turn. If your
  line is addressed to the other character, it must not also pose a question
  to the student — leave that entirely to whoever speaks last this turn.
{participation_text}
IF THE STUDENT ASKS FOR HELP
If they ask how to say something, ask you to repeat, to speak more slowly, or
say they did not understand: help them immediately and warmly, in character.
Give them the word or phrase, or repeat using simpler words. Then continue the
scene. This is never a reason to be impatient.

CRITICAL RULES
- QUESTION FORMAT (this overrides how you resist and what you ask for):
  {content.questions} This limit is per TURN, not per line: either you ask
  this turn's question yourself, or you hand the floor to the other character
  and THEY ask it. Express your resistance and your conditions to concede
  ONLY within this format.
- Every question is about the student's own experience, preferences or
  situation — never about whether they know a concept, and never about a
  technology or tool they did not mention. Right: "Did you work in a team on
  that project?" Wrong: "Do you know what a JOIN is?"
- Never answer your own question, and never say what the student should
  answer. Your line is only YOUR part of the conversation; the kind of answer
  expected goes only in the hint.
- Stay in character. You are NOT an English teacher and you never grade or
  correct the student's grammar or vocabulary.
- Speak DIRECTLY to the student (use "you") in every line, UNLESS you are
  handing the floor to the other character this turn — that is the only
  case where your line addresses them instead (see "pass_to" below).
- Your spoken line is English only.
- Never reveal what the student must do to succeed. Do not coach the task.
- Speak ONLY as {role.name}.

- "hint": help for the student, written in PORTUGUESE. This is the only text
  you ever write in Portuguese. It tells the student how to answer YOUR
  question, in the answer format this level expects ({content.expected_production})
  — for example, which options they can choose from, or what the yes/no is
  about. Write it about this specific question; never copy or describe the
  level itself. Maximum 14 words. Never write the English sentence for them.
- "pass_to": "student" when this line is addressed to the student; one of
  {valid_keys} when this line is addressed to that character instead, and they
  should respond right now, in this same turn.
- "scene_resolved": true ONLY when the student already obtained what they
  wanted from you and there is nothing left to negotiate. Your line should
  then close the interaction naturally."""


_QUESTION = re.compile(r"[^.!?]*\?")
_FALLBACK_WITHOUT_QUESTION = "Sorry, let me ask again. Are you ready to continue?"


def fallback_line(role: Role, history: list) -> str:
    """Fala usada quando o modelo não produz nenhuma fala para a persona na rodada.

    Repete a última pergunta que a própria persona fez, com uma introdução curta: essa
    pergunta já seguia o formato do nível, e o aluno nunca fica sem resposta. Sem
    pergunta anterior, usa uma frase fixa, curta e fechada.
    """
    prefix = f"[{role.name}]"
    for message in reversed(history):
        text = message.content or ""
        if not text.startswith(prefix):
            continue
        questions = _QUESTION.findall(text[len(prefix) :])
        if questions:
            return f"Let me ask again: {questions[-1].strip()}"
    return _FALLBACK_WITHOUT_QUESTION


_CLOSING_PROMPT = """You are {name}, {scene_function}, talking to a student who is
practising English. The conversation has just run out of time.

Last exchanges:
{excerpt}

Write your FINAL line, in character: one or two short sentences in English that
close the conversation. Acknowledge what the student said and state what happens
next, or that you have to go.

Hard requirement: your line MUST NOT contain a question. No question marks."""


def generate_closing_line(content: ScenarioContent, role: Role, history: list) -> str:
    """Gera a última fala da cena com um prompt curto e sem histórico longo.

    Chamada própria porque, no prompt completo, o padrão de perguntar dos
    turnos anteriores prevalece sobre a instrução de encerrar.
    """
    prompt = _CLOSING_PROMPT.format(
        name=role.name,
        scene_function=role.scene_function,
        excerpt=transcript_text(history, last=3),
    )
    llm = get_structured_llm(ModelPurpose.PERSONA, ClosingLine)

    for _ in range(2):
        turn = llm.invoke([HumanMessage(content=prompt)])
        text = sanitize_line(turn.line)
        if text and "?" not in text:
            return text

    return "Thank you for your time today. Let's continue this later."


_CLOSING_HINT_PROMPT = """You are {name}, {scene_function}, talking to a student who is
practising English. Keep your English simple.

Last exchanges:
{excerpt}

Your next line MUST do exactly this:
{hint}

One or two short sentences, in character. Nothing else."""


def generate_closing_hint_turn(
    content: ScenarioContent, role: Role, history: list
) -> tuple[str, str]:
    """Gera a fala que abre a oportunidade para os critérios do cenário.

    Chamada dedicada e curta, pela mesma razão do fechamento: no prompt completo
    o padrão de perguntar dos turnos anteriores prevalece e a instrução é
    ignorada. Sem esta abertura, critérios que dependem de uma pergunta do
    aluno ficam inalcançáveis.
    """
    prompt = _CLOSING_HINT_PROMPT.format(
        name=role.name,
        scene_function=role.scene_function,
        excerpt=transcript_text(history, last=3),
        hint=content.closing_hint,
    )
    llm = get_structured_llm(ModelPurpose.PERSONA, ClosingHintTurn)
    turn = llm.invoke([HumanMessage(content=prompt)])
    return sanitize_line(turn.line), turn.hint
