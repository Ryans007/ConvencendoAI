import re
from collections.abc import Sequence
from dataclasses import dataclass

from langchain_core.messages import BaseMessage, HumanMessage

from apps.agents.services.scenario_content import ScenarioContent
from apps.agents.services.schemas import EvaluationResult, ReviewItem
from apps.agents.services.transcript import answered_after_hint, transcript_text
from apps.catalog.constants import RubricDimension
from apps.llm.constants import ModelPurpose
from apps.llm.services.factory import get_structured_llm

# Pronúncia fica fora: a execução é sempre por texto, sem áudio para julgar. A
# dimensão "objetivo" também fica fora daqui — é uma checklist calculada em
# `apps.progress.services.scoring`, nunca um julgamento do modelo.
JUDGED_DIMENSIONS = [
    RubricDimension.FLUENCY,
    RubricDimension.VOCABULARY,
    RubricDimension.GRAMMAR,
    RubricDimension.PRAGMATICS,
    RubricDimension.AUTONOMY,
]

_DIMENSION_GUIDANCE = {
    RubricDimension.FLUENCY: (
        "smoothness and clarity of the student's utterances, and hesitation. Length only "
        "counts when the level's format asks for developed answers."
    ),
    RubricDimension.VOCABULARY: (
        "precision of the words used. Range and variety only count when the level's "
        "format asks for developed answers; basic words are fine at the lower levels."
    ),
    RubricDimension.GRAMMAR: "accuracy; count real errors, ignore transcription noise.",
    RubricDimension.PRAGMATICS: (
        "register appropriate to the role (politeness, firmness). If the student got "
        "what they wanted by being rude or by issuing commands, this score must be low."
    ),
    RubricDimension.AUTONOMY: "did the student ask for help, switch to Portuguese, or give up?",
}

_HINTS_NOTE = """
SUGGESTED ANSWERS
Turns marked "Student (after a suggested answer)" came after the student asked for help
and saw a suggested answer, written in Portuguese, which they then said in English. Count
those turns as less autonomous in the autonomy score, in proportion to how many there
are. Judge every other dimension, and the acceptance criteria, exactly as for any other
turn: saying the suggestion in English is still the student's own English.
"""

_PROMPT = """You are a strict but fair English examiner. You will grade a
student's performance in a role-play task. The student is a Brazilian
professional practising spoken English.

CALIBRATION — READ FIRST
This task was set at difficulty "{difficulty}", where the expected level is
{expected_cefr}. Grade the linguistic dimensions RELATIVE to that level: a
student who performs solidly at {expected_cefr} deserves around 80% of each
maximum. Do not penalise them for not sounding like a C1 speaker. Reserve
low scores for what genuinely blocks communication.

WHAT THIS LEVEL ASKS OF THE STUDENT
"{expected_production}"
Judge length, range and fluency AGAINST THIS FORMAT, not against free
conversation. If the level asks for yes/no or short answers, a clear short
answer is exactly what was asked: it is NOT a weakness, so do not lower any
score for it and never mention its brevity as something to improve.

TASK GOAL
{objective}

ACCEPTANCE CRITERIA AND WHAT THE STUDENT ACHIEVED
{criteria_status}

TRANSCRIPT (the student's turns are marked "Student:")
{transcript}
{hints_note}
Grade ONLY these dimensions, each from 0 up to its maximum:
{dimensions}

Guidance:
{guidance}

Also decide:
- "confirmed_criteria": going through the WHOLE transcript, the ids of every
  acceptance criterion that was genuinely satisfied. Be strict: the student must
  have actually produced it, not merely implied it. Some criteria depend on what
  the other characters answered (for example, obtaining an explicit
  confirmation), so check the characters' replies too, not only the student's.

Also write:
- "feedback": 2-3 sentences addressed to the student, in English, saying what
  worked and the single most important thing to improve. Never present as
  something to improve what the level's format asks for (for example, short
  answers when the level asks for short answers).
- "memory_summary": 3-4 very short factual notes in English about this
  student, to be remembered in a future conversation (role, project mentioned,
  commitments made, recurring language difficulty). Third person, no grades.
- "review_items": up to 4 concrete mistakes the student made, about WORDS or
  STRUCTURE only. Never pronunciation or sounds: you only have the transcript, not
  the audio. For each one:
  - "rule": the general rule broken, short, in English (for example "past simple
    with a finished time expression"), never the sentence itself;
  - "produced": the WHOLE sentence the student said, with the mistake inside it,
    never just the wrong word or fragment;
  - "correct": that same whole sentence, corrected. Keep what the student meant:
    never change the request, the topic or the facts. If the mistake cannot be
    corrected without guessing something else the student wanted, do not report it;
  - "note": ONE short sentence in Brazilian Portuguese that tells the student what
    to look at in that sentence, describing the idea in Portuguese. It must NEVER
    contain the correct English word, phrase or structure. Good: "Aqui o verbo é o de
    consertar, e não o de relatar." Bad: "Use 'repair', não 'report'." (it gives the
    answer away). When the wrong word sounds like the right one, say so: "Essas duas
    palavras soam parecidas; atenção ao verbo que expressa querer.";
  - "repeats": the id of a KNOWN MISTAKE below when this mistake breaks the SAME
    rule, even with different words (for example "I have worked there yesterday"
    and "I have finished it last week" are the same rule); otherwise "".
  Choosing the mistakes:
  - The transcript is what automatic speech recognition heard, and it is the only
    evidence you have. A wrong word in it is the student's mistake even when it may
    have been a mispronunciation: "I won a floor" is a mistake when the student
    clearly meant "want". Report it only when the word the student meant is clear
    from the situation; if you would be guessing, skip it.
  - Report only mistakes of wording or grammar that have a clear correct form.
    Never report rudeness, register, what the student decided to say, or a
    sentence that simply makes no sense.
  - If there are more than 4, prefer grammar structure mistakes that a learner
    tends to repeat (a preposition after a verb, word order, agreement, tense) over
    one-off vocabulary slips.

KNOWN MISTAKES OF THIS STUDENT (rules from earlier sessions, with their ids)
{known_rules}"""


MAX_REVIEW_ITEMS = 4
_NO_KNOWN_RULES = "(none yet)"


@dataclass(frozen=True)
class KnownRule:
    """Uma regra que o aluno já tem para revisar, com o identificador que o avaliador cita."""

    id: str
    rule: str


@dataclass(frozen=True)
class JudgedDimension:
    """A sub-nota de uma dimensão linguística julgada pelo modelo, já limitada ao peso."""

    dimension: str
    value: int
    weight: int


@dataclass(frozen=True)
class EvaluationOutcome:
    """Resultado bruto do julgamento de uma execução.

    Não inclui a dimensão "objetivo" nem a nota final: essas são calculadas por
    `apps.progress.services.scoring`, a partir dos critérios confirmados aqui.
    """

    confirmed_criteria: set[str]
    judged_dimensions: list[JudgedDimension]
    feedback: str
    memory_summary: str
    review_items: list[ReviewItem]


def evaluate(
    content: ScenarioContent,
    messages: list[BaseMessage],
    known_rules: Sequence[KnownRule] = (),
) -> EvaluationOutcome:
    """Avalia a execução de um cenário: julga as dimensões linguísticas e confirma
    os critérios de aceite satisfeitos, a partir da transcrição inteira.

    É a única etapa que valida os critérios de aceite — uma chamada ao modelo, ao
    fim da execução. As sub-notas voltam sempre limitadas ao peso da dimensão, para
    nunca confiar na aritmética do modelo.

    As falas que o aluno deu depois de ver uma dica saem marcadas na transcrição, e só
    quando há alguma o prompt explica a marca: ela pesa apenas na autonomia, porque dizer
    em inglês a sugestão em português continua sendo o inglês do próprio aluno.

    Os erros de revisão vêm com a regra por trás de cada um, e `known_rules` são as regras
    que o aluno já tem: o avaliador diz quando um erro novo é a mesma regra de uma delas,
    porque é a regra, e não o trecho, que se revisa. Um `repeats` que não está entre as
    conhecidas é ignorado, um erro sem regra ou sem as duas formas é descartado, e passam
    no máximo 4.
    """
    criteria_status = "\n".join(f"- {c.code}: {c.text}" for c in content.criteria)
    dimensions_text = "\n".join(
        f"- {dimension}: max {content.weights.get(dimension, 0)}"
        for dimension in JUDGED_DIMENSIONS
    )
    guidance_text = "\n".join(
        f"- {dimension}: {_DIMENSION_GUIDANCE[dimension]}" for dimension in JUDGED_DIMENSIONS
    )

    prompt = _PROMPT.format(
        difficulty=content.difficulty_label,
        expected_cefr=content.expected_cefr,
        expected_production=content.expected_production,
        objective=content.objective,
        criteria_status=criteria_status,
        transcript=transcript_text(messages, mark_hints=True),
        hints_note=_HINTS_NOTE if any(answered_after_hint(m) for m in messages) else "",
        dimensions=dimensions_text,
        guidance=guidance_text,
        known_rules="\n".join(f"- {known.id}: {known.rule}" for known in known_rules)
        or _NO_KNOWN_RULES,
    )

    llm = get_structured_llm(ModelPurpose.JUDGE, EvaluationResult)
    result = llm.invoke([HumanMessage(content=prompt)])

    valid_codes = {c.code for c in content.criteria}
    confirmed = {code for code in result.confirmed_criteria if code in valid_codes}

    judged_dimensions = [
        JudgedDimension(
            dimension=dimension,
            value=int(max(0, min(weight, round(result.sub_scores.get(dimension, 0))))),
            weight=weight,
        )
        for dimension in JUDGED_DIMENSIONS
        for weight in [content.weights.get(dimension, 0)]
    ]

    return EvaluationOutcome(
        confirmed_criteria=confirmed,
        judged_dimensions=judged_dimensions,
        feedback=result.feedback.strip(),
        memory_summary=result.memory_summary.strip(),
        review_items=_usable_review_items(result.review_items, known_rules),
    )


_WORD = re.compile(r"[a-z]+(?:'[a-z]+)*", re.IGNORECASE)
_MIN_FIX_WORD_LENGTH = 4
_MAX_INFLECTION_DIFFERENCE = 3
_MASK = "___"


def _same_word_family(word: str, fix_word: str) -> bool:
    """Uma palavra é a palavra que conserta o erro, ou uma variação dela (repair, repaired).

    Vale quando uma é o começo da outra e o comprimento difere pouco: assim "repaired" na nota
    casa com "repair" na correção, sem casar com uma palavra comprida qualquer que só comece
    igual.
    """
    shorter, longer = sorted((word, fix_word), key=len)
    return (
        len(shorter) >= _MIN_FIX_WORD_LENGTH
        and longer.startswith(shorter)
        and len(longer) - len(shorter) <= _MAX_INFLECTION_DIFFERENCE
    )


def _masked_note(item: ReviewItem) -> str:
    """A nota do item, com as palavras que entregam a resposta trocadas por "___".

    A nota existe para dar o contexto sem dar o inglês correto, e a instrução do prompt sozinha
    não garante isso: medido com o modelo real, metade das notas trazia algo como "use
    'repair'". As palavras que consertam o erro são as da forma corrigida que não estão na frase
    do aluno; cada uma delas, ou variação dela, com 4 letras ou mais, vira "___" na nota. O
    contexto que sobra ("___ para consertar, não 'report'") continua útil, e a resposta não
    chega ao aluno. Palavras curtas ("to", "for") ficam de fora porque aparecem em qualquer
    texto em português que cita uma preposição.
    """
    note = item.note.strip()
    if not note:
        return ""
    produced_words = {word.lower() for word in _WORD.findall(item.produced)}
    fix_words = {
        word.lower()
        for word in _WORD.findall(item.correct)
        if word.lower() not in produced_words and len(word) >= _MIN_FIX_WORD_LENGTH
    }

    def mask(match: re.Match) -> str:
        word = match.group(0).lower()
        return _MASK if any(_same_word_family(word, fix) for fix in fix_words) else match.group(0)

    return _WORD.sub(mask, note)


def _usable_review_items(
    items: list[ReviewItem], known_rules: Sequence[KnownRule]
) -> list[ReviewItem]:
    """Os erros que podem virar item de revisão, com `repeats` só apontando regra conhecida.

    Um item sem a frase, sem a forma correta ou sem a regra não serve para revisar e é
    descartado. Já um item sem nota continua valendo, só sem o contexto extra.
    """
    known_ids = {known.id for known in known_rules}
    usable = [
        item.model_copy(
            update={
                "rule": item.rule.strip(),
                "produced": item.produced.strip(),
                "correct": item.correct.strip(),
                "note": _masked_note(item),
                "repeats": item.repeats if item.repeats in known_ids else "",
            }
        )
        for item in items
        if item.rule.strip() and item.produced.strip() and item.correct.strip()
    ]
    return usable[:MAX_REVIEW_ITEMS]
