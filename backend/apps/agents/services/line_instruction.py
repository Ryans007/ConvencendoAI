from apps.agents.services.participation import SceneParticipation
from apps.agents.services.scenario_content import Role

_NO_QUESTION_HEADER = "THIS LINE (this overrides every rule above about questions)"
_LINE_START_HEADER = "THIS LINE (this overrides every rule above about how your line starts)"

_HANDOFF_LINE = """
You are handing the floor to {name} now. Write one or two short sentences, spoken to the student.
First a brief reaction that shows you heard what the student just said (mention their choice,
fact or answer, not only "thank you"), without agreeing to, granting or deciding anything new in
this line. Then tell the student, as a statement and in your own words, that {name} continues,
naming {name}. Read the conversation first: never reuse a sentence that you or anyone already
used to hand over the floor, such as "{name} will take it from here"; say it differently. Your
line has NO question and NO question mark at all: {name} asks the student this turn's question
right after you."""

_REDIRECT_LINE = """
The student's last message is about {name}'s area in this scene ({function}), not yours.
Write ONE short sentence, spoken to the student, saying in your own words that {name} is the
right person for that. Name {name} only once, as the subject of the sentence: do not call {name}
at the start or at the end of it. Do not answer the subject yourself. Your line has NO question
and NO question mark at all: {name} answers the student right after you."""

_RECEIVED_LINE = """
{previous} has just handed the floor to you, in this same turn. {previous}'s line was a handover
said to the student, not a question for you: never answer it, repeat it or contradict it. You are
{name}, {function}, not the student.
{debut}Answer or react briefly to what the STUDENT said in their last message.
Then ask the student this turn's question, about their own experience."""

_SUPPORTING_FIRST_LINE = """
You step in briefly as {name}, {function}: you do not lead this scene.
In at most two short sentences, answer what the student just said or give the fact your role knows
about it. Your line has NO question and NO question mark at all: {leader} asks the student
this turn's question right after you."""

_SUPPORTING_FOLLOWS_LINE = """
The student's last message was addressed to you. Answer it or react to it in one or two short
sentences. Your line has NO question and NO question mark at all: {supporting} speaks right after
you, in this same turn, and asks the student this turn's question. Do not address {supporting}
by name."""

_SUPPORTING_CLOSES_LINE = """
{previous} has just spoken in this same turn, and that line was not a question for you. You are
{name}, {function}, a supporting character, not the student.
Answer what was said to you or give the fact your role knows, in at most two short
sentences, then finish with ONE short question to the student about your part of the scene.
{previous} keeps leading the conversation."""

_DEBUT_LINE = """
You have not spoken yet in this conversation.
Start your line by introducing yourself: your name and your role ({function}, said in English).
Then answer or react briefly to what the student said, and ask the student this turn's question."""

_DEBUT_STEP = (
    "Start your line by introducing yourself: your name and your role ({function}, said in "
    "English).\n"
)


def is_debut(
    role: Role,
    participation: SceneParticipation | None,
    redirect_to: Role | None = None,
    hand_floor_to: Role | None = None,
) -> bool:
    """A persona estreia nesta fala: ainda não falou na conversa e não está só passando a vez.

    Quem passa a vez ou redireciona fala uma frase curta e sai, então não se apresenta ali. Sem
    a participação, como na abertura da cena, não há estreia a anunciar.
    """
    return (
        participation is not None
        and redirect_to is None
        and hand_floor_to is None
        and participation.lines_by_role.get(role.key, 0) == 0
    )


def line_instruction(
    role: Role,
    participation: SceneParticipation | None = None,
    redirect_to: Role | None = None,
    hand_floor_to: Role | None = None,
    received_from: Role | None = None,
    supporting_first_before: Role | None = None,
    supporting_closes_after: Role | None = None,
    supporting_follows: Role | None = None,
) -> str:
    """O que esta fala tem de fazer na rodada, para ir depois da conversa, ou vazio.

    Os parâmetros são os mesmos marcadores de rodada de `build_system_prompt`. O system prompt
    traz blocos de turno no meio e termina com `CRITICAL RULES`, que manda sempre terminar com a
    pergunta da rodada e começar respondendo ao aluno: medido com o modelo real, quem passava a
    vez perguntava ao aluno em 19 de 60 falas, e quem estreava não se apresentava em 12 de 48,
    porque obedecia ora a um bloco, ora à regra. Esta instrução é curta, declara precedência
    sobre as regras e é a última coisa lida; com ela, 0 de 60 e 0 de 48.

    Quem passa a vez fala ao aluno sobre o colega ("Tom will ask you next"), sem vocativo, e
    quem recebe é avisado de que a fala anterior não é uma pergunta para ele: medido, sem o
    aviso, o tech lead respondia à pergunta da recrutadora como se fosse o candidato. As falas
    sem pergunta não passam por filtro: a instrução é o que garante a ausência de pergunta.

    Sem nenhum marcador, só a persona que estreia recebe instrução, como quando o aluno a chama
    pelo nome antes de ela ter falado: medido numa negociação simulada, o tech lead chamado pelo
    aluno entrou sem dizer quem era.

    O passo de apresentação vale só para as personas principais, que conduzem a cena e o aluno
    ainda não conhece. O coadjuvante entra para confirmar um fato e pode ser alguém que o aluno
    conhece: medido, com o passo, a amiga do aluno abria com "Hi, I'm Mia, your friend" e deixava
    de dar a informação que a cena esperava dela.
    """
    debut_step = (
        _DEBUT_STEP.format(function=role.scene_function)
        if not role.supporting and is_debut(role, participation, redirect_to, hand_floor_to)
        else ""
    )
    if hand_floor_to is not None:
        body = _HANDOFF_LINE.format(name=hand_floor_to.name)
        return f"{_NO_QUESTION_HEADER}\n{body.strip()}"
    if redirect_to is not None:
        body = _REDIRECT_LINE.format(name=redirect_to.name, function=redirect_to.scene_function)
        return f"{_NO_QUESTION_HEADER}\n{body.strip()}"
    if supporting_first_before is not None:
        body = _SUPPORTING_FIRST_LINE.format(
            name=role.name,
            function=role.scene_function,
            leader=supporting_first_before.name,
        )
        return f"{_NO_QUESTION_HEADER}\n{body.strip()}"
    if supporting_follows is not None:
        body = _SUPPORTING_FOLLOWS_LINE.format(supporting=supporting_follows.name)
        return f"{_NO_QUESTION_HEADER}\n{body.strip()}"
    if received_from is not None:
        body = _RECEIVED_LINE.format(
            previous=received_from.name,
            name=role.name,
            function=role.scene_function,
            debut=debut_step,
        )
        return f"{_LINE_START_HEADER}\n{body.strip()}"
    if supporting_closes_after is not None:
        body = _SUPPORTING_CLOSES_LINE.format(
            previous=supporting_closes_after.name,
            name=role.name,
            function=role.scene_function,
        )
        return f"{_LINE_START_HEADER}\n{body.strip()}"
    if debut_step:
        body = _DEBUT_LINE.format(function=role.scene_function)
        return f"{_LINE_START_HEADER}\n{body.strip()}"
    return ""
