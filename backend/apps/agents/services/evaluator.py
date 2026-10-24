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
from apps.progress.services.speech_metrics import SessionSpeechMetrics

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

_SPEECH_NOTE = """
SPEECH MEASUREMENTS (measured from the timing of the student's recorded turns)
{lines}
These numbers were measured, so never contradict them.{fluency}{vocabulary} The fluency and
vocabulary comments may cite these numbers.
"""

_SPEECH_FLUENCY_SCOPE = (
    " Your fluency score must judge only what the numbers cannot see: whether the speech was "
    "understandable and whether the student corrected themselves mid-sentence."
)
_SPEECH_VOCABULARY_SCOPE = (
    " Your vocabulary score must judge only whether each word was the right one for the context."
)

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
{hints_note}{speech_note}
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
- "feedback": 3-5 sentences addressed to the student, in Brazilian Portuguese,
  saying what worked, the single most important thing to improve and why it
  matters in this kind of conversation. Never present as something to improve
  what the level's format asks for (for example, short answers when the level
  asks for short answers).
- "comments": for each judged dimension, ONE sentence in Brazilian Portuguese
  addressed to the student explaining that score with something concrete from
  the conversation.
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
    never change the request, the topic or the facts. Change ONLY the words that
    make the sentence wrong: never add a word the sentence did not need, such as a
    new verb, to fit a structure you prefer. If the mistake cannot be corrected
    without guessing something else the student wanted, do not report it;
  - "note": ONE short sentence in Brazilian Portuguese that tells the student what
    to look at in that sentence, describing the idea in Portuguese. It must NEVER
    contain the correct English word, phrase or structure. Good: "Aqui o verbo é o de
    consertar, e não o de relatar." Bad: "Use 'repair', não 'report'." (it gives the
    answer away). When the wrong word sounds like the right one, say so: "Essas duas
    palavras soam parecidas; atenção ao verbo que expressa querer.";
  - "explanation": one or two short sentences in Brazilian Portuguese explaining
    the rule to the student. Unlike the note, it is shown after the session and
    may write the correct English form;
  - "examples": exactly two short English sentences that apply the same rule in
    situations different from the student's sentence;
  - "repeats": the id of a KNOWN MISTAKE below when this mistake breaks the SAME
    rule, even with different words (for example "I have worked there yesterday"
    and "I have finished it last week" are the same rule); otherwise "".
  Choosing the mistakes:
  - First make sure the sentence is really wrong. A sentence that is correct
    English is NOT a mistake, even when you would phrase it differently: "I would
    like your phone number" is correct, because "would like" takes a noun directly
    and needs "to" only before a verb. Never invent a rule to justify an item; if
    you are not sure the sentence breaks a real rule, skip it.
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
MAX_EXAMPLES = 2
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
    comment: str = ""


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


class IncompleteEvaluation(Exception):
    """O avaliador não devolveu nota para alguma dimensão julgada, nem na retentativa."""


def _judge_with_scores(llm, prompt: str) -> EvaluationResult:
    """Chama o avaliador e garante que toda dimensão julgada veio com nota.

    Uma nota ausente não pode virar 0: reprovaria o aluno por uma falha do modelo, sem
    ninguém perceber. Por isso a chamada é repetida uma vez e, se ainda faltar nota,
    levanta `IncompleteEvaluation` — a tentativa continua aberta e pode ser avaliada de
    novo, porque quem grava o resultado é idempotente.
    """
    missing: list[str] = []
    for _ in range(2):
        result = llm.invoke([HumanMessage(content=prompt)])
        missing = [d.value for d in JUDGED_DIMENSIONS if getattr(result.sub_scores, d.value) is None]
        if not missing:
            return result
    raise IncompleteEvaluation(f"avaliador sem nota para: {', '.join(missing)}")


def evaluate(
    content: ScenarioContent,
    messages: list[BaseMessage],
    known_rules: Sequence[KnownRule] = (),
    speech_metrics: SessionSpeechMetrics | None = None,
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

    O resumo e os comentários de cada dimensão são escritos em português, para o aluno. Quando
    a sessão de voz tem medidas de fala, elas entram prontas no prompt: o modelo não reavalia
    o que já foi medido e pode citar os números nos comentários.
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
        speech_note=_speech_note(speech_metrics),
        dimensions=dimensions_text,
        guidance=guidance_text,
        known_rules="\n".join(f"- {known.id}: {known.rule}" for known in known_rules)
        or _NO_KNOWN_RULES,
    )

    llm = get_structured_llm(ModelPurpose.JUDGE, EvaluationResult)
    result = _judge_with_scores(llm, prompt)

    valid_codes = {c.code for c in content.criteria}
    confirmed = {code for code in result.confirmed_criteria if code in valid_codes}

    judged_dimensions = [
        JudgedDimension(
            dimension=dimension,
            value=int(max(0, min(weight, round(getattr(result.sub_scores, dimension.value))))),
            weight=weight,
            comment=getattr(result.comments, dimension.value).strip(),
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


def _speech_note(metrics: SessionSpeechMetrics | None) -> str:
    """A seção do prompt com as medidas de fala, ou vazia quando não há nada medido.

    Só aparecem as medidas que a sessão tem, e só se pede ao modelo que restrinja a nota de
    fluência ou de vocabulário quando a medida correspondente existe: sem ela, a nota daquela
    dimensão continua sendo inteira do julgamento dele.
    """
    if metrics is None:
        return ""
    lines = []
    if metrics.reaction_seconds is not None:
        lines.append(f"- median time to start answering: {metrics.reaction_seconds:.1f} s")
    if metrics.words_per_minute is not None:
        lines.append(f"- speaking speed: {metrics.words_per_minute:.0f} words per minute")
    if metrics.long_pauses_per_100_words is not None:
        lines.append(
            "- long pauses (over 1.5 s) inside a turn: "
            f"{metrics.long_pauses_per_100_words:.1f} per 100 words"
        )
    if metrics.lexical_diversity is not None:
        lines.append(f"- word variety (MATTR, 0 to 1): {metrics.lexical_diversity:.2f}")
    if metrics.lexical_range is not None:
        lines.append(
            f"- words outside the 2,000 most common in English: {metrics.lexical_range:.0%}"
        )
    if not lines:
        return ""
    return _SPEECH_NOTE.format(
        lines="\n".join(lines),
        fluency=_SPEECH_FLUENCY_SCOPE if metrics.reaction_seconds is not None else "",
        vocabulary=_SPEECH_VOCABULARY_SCOPE if metrics.lexical_diversity is not None else "",
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


def _usable_examples(examples: Sequence[str]) -> list[str]:
    """Os exemplos que servem para o relatório: sem os vazios e no máximo dois."""
    return [example.strip() for example in examples if example.strip()][:MAX_EXAMPLES]


def _usable_review_items(
    items: list[ReviewItem], known_rules: Sequence[KnownRule]
) -> list[ReviewItem]:
    """Os erros que podem virar item de revisão, com `repeats` só apontando regra conhecida.

    Um item sem a frase, sem a forma correta ou sem a regra não serve para revisar e é
    descartado. Já um item sem nota, sem explicação ou sem exemplos continua valendo, só sem o
    que faltou.
    """
    known_ids = {known.id for known in known_rules}
    usable = [
        item.model_copy(
            update={
                "rule": item.rule.strip(),
                "produced": item.produced.strip(),
                "correct": item.correct.strip(),
                "note": _masked_note(item),
                "explanation": item.explanation.strip(),
                "examples": _usable_examples(item.examples),
                "repeats": item.repeats if item.repeats in known_ids else "",
            }
        )
        for item in items
        if item.rule.strip() and item.produced.strip() and item.correct.strip()
    ]
    return usable[:MAX_REVIEW_ITEMS]
