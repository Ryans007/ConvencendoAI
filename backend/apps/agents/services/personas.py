import re

from langchain_core.messages import HumanMessage

from apps.agents.services.participation import SceneParticipation
from apps.agents.services.schemas import ClosingLine
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


_TAKING_OVER_TEXT = """
YOU ARE TAKING THE LEAD NOW
Until now the other character was leading the conversation, and the student's last
message was an answer to them. React briefly to that answer (one short sentence), then
ask this turn's question to the student yourself. Do not hand the floor back in this line.
"""

_DECIDER_OUTCOME = """You decide this."""

_NOT_DECIDER_OUTCOME = """You do NOT decide this: {deciders} does. Never grant it, promise it or
confirm it yourself. When the student asks you for it, support them and hand the decision to
the one who decides."""

_ADDRESSED_BY_STUDENT_TEXT = """
THE STUDENT IS TALKING TO YOU
The student's last message was addressed to you, not to the other character. Answer it
or react to it first, as described in CRITICAL RULES. This line closes the round: do not
hand the floor to the other character.
"""


_REDIRECT_TEXT = """
THIS SUBJECT IS NOT YOUR AREA
The student's last message is about {name}'s area in this scene ({function}), not yours.
Your line is ONE short sentence in your own words, with NO question: say that {name} is the
right person for that, and address {name} by name. {name} answers right after you, in this
same turn. Do not answer the subject yourself and do not give an opinion about it.
"""

_DEBUT_TEXT = """
THIS IS YOUR FIRST LINE IN THE CONVERSATION
You have not spoken yet. Start your line by introducing yourself in a few words: your name
and your role in this scene ({function}, said in English), for example
"Hi, I'm {name}, the <your role in English>." Then react briefly to what the student said
and ask this turn's question.
"""

_RECEIVED_TEXT = """
{name} JUST HANDED THIS TO YOU
The student's last message is about your area in this scene, and {name} passed it to you in
this same turn. Answer what the student said or asked first, then ask this turn's question
to the student yourself. Do not hand the floor back in this line.
"""


TRANSCRIPTION_NOTICE = """
HOW YOU RECEIVE WHAT THE STUDENT SAYS
The student speaks, and what you read is an automatic voice transcription, so a word may
have been swapped for another that sounds alike (for example "I won" for "I want"). When a
word makes no sense in the situation, read the message as what the student most likely
meant, and answer that. Never mention, correct or comment on the transcription, and never
turn this example into a topic of conversation.
"""


def build_system_prompt(
    content: ScenarioContent,
    role: Role,
    memory: str,
    adaptation_line: str = "",
    participation: SceneParticipation | None = None,
    taking_over: bool = False,
    addressed_by_student: bool = False,
    redirect_to: Role | None = None,
    received_from: Role | None = None,
) -> str:
    """Monta o system prompt do papel para esta execução.

    O formato de pergunta do nível aparece em `CRITICAL RULES` com precedência declarada
    sobre a resistência da persona: medido em teste real, a resistência cadastrada no
    cenário ("pede exemplos concretos") vencia a regra do nível quando as duas apareciam
    com o mesmo peso no prompt.

    O aviso de transcrição (`TRANSCRIPTION_NOTICE`) entra logo antes de `CRITICAL RULES`,
    para as regras continuarem sendo a última coisa lida. Sem ele, medido com o modelo real,
    4 de 8 falas tratavam "I won a wood floor" como uma vitória; com ele, 0 de 8.

    Com `taking_over`, a persona está assumindo a conversa pelo equilíbrio de turno: a
    última fala do aluno respondeu a outro personagem, e é ela quem faz a transição.

    Com `addressed_by_student`, o roteador reconheceu que o aluno falou com esta persona:
    ela responde primeiro e fecha a rodada, sem passar a vez. A regra de responder ao que o
    aluno diz vale mesmo sem a marca, porque uma pergunta feita sem nomear ninguém (por
    exemplo, sobre os próximos passos) também é dirigida a quem está falando com ele; a
    marca só reforça o caso em que há certeza.

    A persona que ainda não falou na conversa recebe o aviso de estreia e se apresenta, por
    qualquer motivo que a tenha trazido à cena (equilíbrio, assunto, chamado do aluno ou
    passagem de vez). Medido com o modelo real, sem o aviso o Tom entrava e se apresentava em 0
    de 6 vezes: o prompt dizia quantas vezes a OUTRA já tinha falado, mas nunca que ela mesma
    estava estreando. A abertura, que não recebe a participação, e a persona que só
    redireciona, que fala uma frase sem pergunta, ficam de fora.

    Com `redirect_to`, o aluno chamou esta persona para um assunto que é da função de
    outro personagem: ela diz numa frase, sem pergunta, que é com ele, e quem recebe a passagem
    (`received_from`) responde primeiro e pergunta. A passagem de vez não é mais uma escolha da
    persona: medido com o modelo real, ela nunca passava a vez por conta própria (0 das 20
    trocas de 5 sessões), então o sistema decide e a persona só escreve a fala.

    A instrução extra do papel, cadastrada no admin, entra num bloco próprio antes das
    regras: é onde o cenário dá à persona os fatos que ela precisa para responder ao
    aluno. O bloco avisa que os fatos servem só para responder: medido em sessões
    simuladas, sem o aviso a persona usava um fato do cadastro para montar a própria
    pergunta (por exemplo, perguntar sobre Django ao aluno que não o citou). Como
    `CRITICAL RULES` vem depois e declara precedência, nenhuma instrução do administrador
    desliga uma regra de comportamento.

    O papel que decide o resultado da cena (`decides_outcome`) cede pelo que o cartão diz, sem
    instrução que o empurre a conceder num turno: a confirmação do que o aluno conseguiu vem na
    fala que abre a oportunidade dos critérios, num turno fixo. O papel que não decide (o
    aliado) nunca concede nem confirma, e devolve a decisão a quem decide.
    """
    other_keys = [key for key in content.role_keys() if key != role.key]
    other_names = {key: content.role(key).name for key in other_keys}
    others_text = ", ".join(f"{name} (key: {key})" for key, name in other_names.items())
    if not others_text:
        others_text = "nobody else"
    participation_text = _participation_text(content, role, participation)
    taking_over_text = _TAKING_OVER_TEXT if taking_over else ""
    addressed_text = _ADDRESSED_BY_STUDENT_TEXT if addressed_by_student else ""
    extra_instruction = role.extra_instruction.strip()
    extra_text = ""
    if extra_instruction:
        extra_text = (
            "\nMORE ABOUT YOUR ROLE IN THIS SCENE\n"
            "(these notes may be written in Portuguese; you still speak only English)\n"
            "Use the facts in these notes ONLY to answer what the student asks you "
            "and to ask about their own experience when it fits your role. Never state "
            "a fact that contradicts them, and never invent a fact that is not here.\n"
            f"{extra_instruction}\n"
        )
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
    if content.decides(role.key):
        outcome_text = _DECIDER_OUTCOME
    else:
        deciders = ", ".join(
            f"{decider.name} (key: {decider.key})" for decider in content.deciders()
        )
        outcome_text = _NOT_DECIDER_OUTCOME.format(deciders=deciders)
    redirect_text = (
        _REDIRECT_TEXT.format(name=redirect_to.name, function=redirect_to.scene_function)
        if redirect_to
        else ""
    )
    received_text = _RECEIVED_TEXT.format(name=received_from.name) if received_from else ""
    debut = (
        participation is not None
        and redirect_to is None
        and participation.lines_by_role.get(role.key, 0) == 0
    )
    debut_text = (
        _DEBUT_TEXT.format(name=role.name, function=role.scene_function) if debut else ""
    )

    return f"""You are {role.name}, {role.scene_function}.
Your interactional role in this scene: {role.archetype}.
What that means (written in Portuguese; you still speak only English): {role.archetype_description}
Personality: {role.traits}
{extra_text}
SCENE
{content.context}

WHAT THE STUDENT WANTS IN THIS SCENE
{content.objective}
{outcome_text}

The other person in the room: {others_text}.

YOUR BEHAVIOUR (always within the QUESTION FORMAT in CRITICAL RULES)
- How you resist: {role.resistance}
- What makes you concede: {role.concession}
{memory_text}{scaffolding_text}
HOW YOU SPEAK (difficulty: {content.difficulty_label})
- {content.language}
- {content.rephrasing}
{adaptation_text}
TECHNICAL QUESTIONS
The student is practising ENGLISH in a realistic scene. When it fits your role, you may
ask about their technical choices and about alternatives (for example "Why did you
choose this approach and not another one?"). Ask about their own experience, decisions
and situation, always within the QUESTION FORMAT in CRITICAL RULES.
- Never quiz them: never ask whether they know a concept or what something is, as in an
  exam.
- Accept what the student tells you about their own work as true.
- When an answer is vague, react as described in HOW YOU SPEAK.

NEVER REPEAT A QUESTION
- Before you speak, read the WHOLE conversation so far, not just the last line.
  Never ask something you or the other character already asked, even if the
  student has not answered it yet, and even if you word it differently. Never
  ask about something the student already answered, even if they answered it
  to the other character.
- If the student could not answer a question after 2 attempts, DROP IT and move
  the conversation to a different subject. Never ask the same question a third
  time, even reworded.

{participation_text}{taking_over_text}{addressed_text}{redirect_text}{received_text}{debut_text}
IF THE STUDENT ASKS FOR HELP
If they ask how to say something, ask you to repeat, to speak more slowly, or
say they did not understand: help them immediately and warmly, in character.
Give them the word or phrase, or repeat using simpler words. Then continue the
scene. This is never a reason to be impatient.
{TRANSCRIPTION_NOTICE}
CRITICAL RULES
- QUESTION FORMAT (this overrides how you resist and what you ask for):
  {content.questions} This limit is per TURN, not per line: either you ask
  this turn's question yourself, or the other character takes the floor right
  after you and THEY ask it. Express your resistance and your conditions to concede
  ONLY within this format. An invitation to the student to go on (for example,
  "Anything else you'd like to know?") counts as this turn's question.
- ANSWER THE STUDENT FIRST: when the student's last message asks YOU something
  or makes a comment to YOU, your line starts by answering it or reacting to
  it. Never skip it to ask your next question. How you do it at this level:
  {content.reply_to_student} Then ALWAYS
  finish the line with this turn's question (or the invitation): a line that
  only answers leaves the student with nothing to say. A plain answer to your
  own question is not a reason to react at length: just continue the
  conversation.
- Every question is about the student's own experience, preferences, decisions or
  situation — never about whether they know a concept. Right: "Did you work in a
  team on that project?" Wrong: "Do you know what a JOIN is?"
- NEVER ASK FOR WHAT YOU ALREADY KNOW: if the student already gave a fact (a room
  number, a date, a name, a reason), even without being asked and even to the other
  character, use it and never ask for it again. Example: after "my room 312", never
  ask for the room number.
- IF THE STUDENT ASKS WHETHER THEIR ENGLISH IS CORRECT: you are a character, not a
  teacher, so you have no opinion about their English. Never say "your English is good /
  fine / clear / understandable", never mention grammar or mistakes, and never repeat
  their sentence in a better form. Answer only about the CONTENT: say that you understood
  what they said (for example "I understood you, three years is good experience."), then
  ask this turn's question.
- Never answer your own question, and never say what the student should
  answer. Your line is only YOUR part of the conversation.
- Stay in character. You are NOT an English teacher and you never grade or
  correct the student's grammar or vocabulary.
- Speak DIRECTLY to the student (use "you") in every line, UNLESS a block above
  tells you to address the other character this turn.
- Your spoken line is English only.
- Never reveal what the student must do to succeed. Do not coach the task.
- Speak ONLY as {role.name}."""


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
{notice}
Last exchanges:
{excerpt}

Write your FINAL line, in character: one or two short sentences in English that
close the conversation. Acknowledge what the student said and state what happens
next, or that you have to go.

Hard requirement: your line MUST NOT contain a question. No question marks."""


def generate_closing_line(content: ScenarioContent, role: Role, history: list) -> str:
    """Gera a última fala da cena com um prompt curto e sem histórico longo.

    Chamada própria porque, no prompt completo, o padrão de perguntar dos
    turnos anteriores prevalece sobre a instrução de encerrar. Pela mesma razão ela não
    herda o aviso de transcrição do prompt principal, então o recebe aqui também.
    """
    prompt = _CLOSING_PROMPT.format(
        name=role.name,
        scene_function=role.scene_function,
        notice=TRANSCRIPTION_NOTICE,
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
{notice}{facts}
Last exchanges:
{excerpt}

If the student's last message asked you something or made a comment to you, start with
one short sentence that answers it or reacts to it. Then your line MUST do exactly this:
{closing_instruction}

At most three short sentences, in character. Nothing else."""

_CLOSING_HINT_FACTS = """
WHAT YOU KNOW ABOUT THIS SCENE (may be written in Portuguese; you speak only English).
Use it only to answer the student, never to build your own question:
{facts}
"""


def generate_closing_hint_line(content: ScenarioContent, role: Role, history: list) -> str:
    """Gera a fala que abre a oportunidade para os critérios do cenário.

    Chamada dedicada e curta, pela mesma razão do fechamento: no prompt completo
    o padrão de perguntar dos turnos anteriores prevalece e a instrução é
    ignorada. Sem esta abertura, critérios que dependem de uma pergunta do
    aluno ficam inalcançáveis.

    Por ser um prompt à parte, ele não herda a regra de responder ao aluno nem os fatos da
    cena do papel: sem eles, uma pergunta do aluno que cai justamente nesta rodada seria
    ignorada e a persona repetiria o convite. Por isso o prompt pede uma frase curta que
    responda ou reaja antes do convite, e traz os fatos do papel quando há e o aviso de
    transcrição.
    """
    extra_instruction = role.extra_instruction.strip()
    facts = (
        _CLOSING_HINT_FACTS.format(facts=extra_instruction) if extra_instruction else ""
    )
    prompt = _CLOSING_HINT_PROMPT.format(
        name=role.name,
        scene_function=role.scene_function,
        notice=TRANSCRIPTION_NOTICE,
        facts=facts,
        excerpt=transcript_text(history, last=3),
        closing_instruction=content.closing_hint,
    )
    llm = get_structured_llm(ModelPurpose.PERSONA, ClosingLine)
    turn = llm.invoke([HumanMessage(content=prompt)])
    return sanitize_line(turn.line)
