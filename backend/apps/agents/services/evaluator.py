from dataclasses import dataclass

from langchain_core.messages import BaseMessage, HumanMessage

from apps.agents.services.scenario_content import ScenarioContent
from apps.agents.services.schemas import EvaluationResult, ReviewItem
from apps.agents.services.transcript import transcript_text
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
    RubricDimension.FLUENCY: "length and smoothness of the student's utterances, hesitation.",
    RubricDimension.VOCABULARY: "range and precision; penalise repetition of basic words.",
    RubricDimension.GRAMMAR: "accuracy; count real errors, ignore transcription noise.",
    RubricDimension.PRAGMATICS: (
        "register appropriate to the role (politeness, firmness). If the student got "
        "what they wanted by being rude or by issuing commands, this score must be low."
    ),
    RubricDimension.AUTONOMY: "did the student ask for help, switch to Portuguese, or give up?",
}

_PROMPT = """You are a strict but fair English examiner. You will grade a
student's performance in a role-play task. The student is a Brazilian
professional practising spoken English.

CALIBRATION — READ FIRST
This task was set at difficulty "{difficulty}", where the expected level is
{expected_cefr}. Grade the linguistic dimensions RELATIVE to that level: a
student who performs solidly at {expected_cefr} deserves around 80% of each
maximum. Do not penalise them for not sounding like a C1 speaker, and do not
penalise short answers that are appropriate and clear at their level. Reserve
low scores for what genuinely blocks communication.

TASK GOAL
{objective}

ACCEPTANCE CRITERIA AND WHAT THE STUDENT ACHIEVED
{criteria_status}

TRANSCRIPT (the student's turns are marked "Student:")
{transcript}

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
  worked and the single most important thing to improve.
- "memory_summary": 3-4 very short factual notes in English about this
  student, to be remembered in a future conversation (role, project mentioned,
  commitments made, recurring language difficulty). Third person, no grades.
- "review_items": up to 4 concrete language items the student got wrong (word,
  structure or sound), each with the form they produced and the correct form."""


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


def evaluate(content: ScenarioContent, messages: list[BaseMessage]) -> EvaluationOutcome:
    """Avalia a execução de um cenário: julga as dimensões linguísticas e confirma
    os critérios de aceite satisfeitos, a partir da transcrição inteira.

    É a única etapa que valida os critérios de aceite — uma chamada ao modelo, ao
    fim da execução. As sub-notas voltam sempre limitadas ao peso da dimensão, para
    nunca confiar na aritmética do modelo.
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
        objective=content.objective,
        criteria_status=criteria_status,
        transcript=transcript_text(messages),
        dimensions=dimensions_text,
        guidance=guidance_text,
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
        review_items=result.review_items,
    )
