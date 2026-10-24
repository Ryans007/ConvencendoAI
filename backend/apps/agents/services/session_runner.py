from django.db import transaction
from django.utils import timezone

from apps.agents.graph.builder import run_scenario as run_graph
from apps.agents.services.evaluator import evaluate
from apps.agents.services.scenario_content import ScenarioContent, load_scenario_content
from apps.catalog.constants import RubricDimension
from apps.catalog.models import Level, Scenario
from apps.progress.choices import EndedBy
from apps.progress.constants import is_passing_score
from apps.progress.models import Attempt, AttemptCriterion, ScoreBreakdown
from apps.progress.services.memory import track_memory
from apps.progress.services.scoring import final_score, objective_score
from apps.progress.services.speech_metrics import session_metrics
from apps.progress.services.speech_scoring import fluency_score, vocabulary_score
from apps.progress.speech_bands import rules_for_level
from apps.review.services.recording import known_rules_for, record_review_items


def resolve_execution(scenario: Scenario, level: Level, user) -> tuple[ScenarioContent, str, Attempt]:
    """Resolve o conteúdo, a memória e abre a tentativa de uma execução — texto ou voz.

    A tentativa nasce aqui, no início da execução, com os campos de resultado vazios
    (mesmo contrato de `Attempt`: `completed_at` só é preenchido quando a execução
    termina de verdade, em `evaluate_and_record_attempt`).
    """
    content = load_scenario_content(scenario, level)
    memory = track_memory(user, scenario)
    attempt = Attempt.objects.create(user=user, scenario=scenario, level=level)
    return content, memory, attempt


_RESULT_FIELDS = [
    "final_score",
    "passed",
    "memory_summary",
    "feedback",
    "ended_by",
    "completed_at",
]


def evaluate_and_record_attempt(
    attempt: Attempt,
    content: ScenarioContent,
    final_state: dict,
    ended_by: str = EndedBy.TURN_LIMIT,
) -> Attempt:
    """Avalia o estado final de uma execução já terminada e grava o resultado na tentativa
    já aberta por `resolve_execution`.

    Reutilizável por qualquer canal: uma execução por texto chama isso uma vez, depois de
    `run_graph` rodar do início ao fim; uma sessão de voz chama isso quando um `ainvoke()`
    devolve um estado sem mais pausa pendente — o fim real da execução, não de um turno.

    Idempotente: para uma tentativa já concluída, devolve a tentativa como está, sem
    chamar o avaliador de novo. A gravação é atômica, para que uma tentativa nunca fique
    marcada como concluída com notas ou critérios pela metade.

    Grava só os campos de resultado: o objeto recebido foi carregado no início da sessão,
    e gravá-lo inteiro apagaria o que mudou na tentativa durante ela, como as dicas usadas.
    `ended_by` registra como a sessão terminou: pelo limite de turnos, que é o padrão, ou a
    pedido do aluno.

    Numa sessão de voz, as vezes de fala gravadas dão as medidas da sessão: elas vão prontas
    ao avaliador e entram nas notas de fluência e vocabulário. Sem vezes gravadas, como na
    execução por texto, as duas notas são o julgamento da IA.

    Os erros de linguagem apontados pelo avaliador viram itens de revisão do aluno na
    mesma transação: o avaliador recebe as regras que o aluno já tem para dizer quando um
    erro se repete.
    """
    if Attempt.objects.filter(pk=attempt.pk, completed_at__isnull=False).exists():
        attempt.refresh_from_db()
        return attempt

    messages = list(final_state.get("messages") or [])
    metrics = session_metrics(
        list(attempt.speech_turns.all()), excluded_names=[role.name for role in content.roles]
    )
    outcome = evaluate(
        content,
        messages,
        known_rules=known_rules_for(attempt.user),
        speech_metrics=metrics,
    )
    rules = rules_for_level(attempt.level.order)

    attempt_criteria = [
        AttemptCriterion(
            code=criterion.code,
            text_at_time=criterion.text,
            met=criterion.code in outcome.confirmed_criteria,
        )
        for criterion in content.criteria
    ]

    objective_weight = content.weights.get(RubricDimension.OBJECTIVE, 0)
    breakdowns = [
        ScoreBreakdown(
            dimension=RubricDimension.OBJECTIVE,
            value=int(round(objective_score(attempt_criteria, objective_weight))),
            weight_at_time=objective_weight,
        )
    ] + [
        ScoreBreakdown(
            dimension=judged.dimension,
            value=_combined_value(judged.dimension, judged.value, judged.weight, metrics, rules),
            weight_at_time=judged.weight,
            comment=judged.comment,
        )
        for judged in outcome.judged_dimensions
    ]

    score = int(round(final_score(breakdowns)))

    attempt.final_score = score
    attempt.passed = is_passing_score(score)
    attempt.memory_summary = outcome.memory_summary
    attempt.feedback = outcome.feedback
    attempt.ended_by = ended_by
    attempt.completed_at = timezone.now()

    with transaction.atomic():
        attempt.save(update_fields=_RESULT_FIELDS)

        for breakdown in breakdowns:
            breakdown.attempt = attempt
        ScoreBreakdown.objects.bulk_create(breakdowns)

        for criterion in attempt_criteria:
            criterion.attempt = attempt
        AttemptCriterion.objects.bulk_create(attempt_criteria)

        record_review_items(
            attempt.user,
            attempt,
            outcome.review_items,
            timezone.localdate(attempt.completed_at),
        )

    return attempt


def _combined_value(dimension, judged_value, weight, metrics, rules) -> int:
    """A sub-nota gravada: fluência e vocabulário combinam o julgamento da IA com as medidas de
    fala; as demais dimensões são o julgamento da IA, já limitado ao peso pelo avaliador.
    """
    if dimension == RubricDimension.FLUENCY:
        return fluency_score(weight, judged_value, metrics, rules)
    if dimension == RubricDimension.VOCABULARY:
        return vocabulary_score(weight, judged_value, metrics, rules)
    return judged_value


def run_and_record_attempt(user, scenario: Scenario, level: Level) -> Attempt:
    """Executa um cenário por texto, do início ao fim, e persiste o resultado.

    É o ponto de encontro entre o núcleo conversacional e a progressão: o núcleo não
    sabe que existe um `Attempt`, e a progressão não sabe que existe um grafo.
    """
    content, memory, attempt = resolve_execution(scenario, level, user)
    final_state = run_graph(content, memory)
    return evaluate_and_record_attempt(attempt, content, final_state)
