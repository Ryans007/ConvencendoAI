from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage

from apps.agents.evaluation.case_loader import NO_ADDRESSEE, RouterCase
from apps.agents.evaluation.output import captured_output
from apps.agents.graph.routing import make_routing_node
from apps.agents.services.round_trace import collect_round_events
from apps.agents.services.scenario_content import ScenarioContent

_ROUTER_FAILURE_MARK = "falha ao decidir roteamento"


class NeutralDraw:
    """Sorteio do equilíbrio de turno neutralizado: só a escolha do aluno é medida.

    Sempre devolve o limite máximo, então o equilíbrio só trocaria a vez depois de rodadas
    demais, e a decisão do roteador sobre quem o aluno chamou fica isolada.
    """

    def randint(self, lower: int, upper: int) -> int:
        return upper


def _topic_owner(events: list[dict[str, Any]]) -> str:
    """O dono do assunto que o modelo do diretor respondeu, lido do evento `direction`.

    É a resposta do modelo, antes das regras do código (o aliado não assume pelo assunto): a
    camada mede o acerto do modelo, e a regra de quem assume é medida nas situações.
    """
    for event in events:
        if event["kind"] == "direction":
            return event["topic_owner"]
    return NO_ADDRESSEE


def run_router_layer(
    cases: list[RouterCase],
    contents: dict[tuple[str, int], ScenarioContent],
    repetitions: int,
    progress: Callable[[str], None] = lambda message: None,
) -> list[dict[str, Any]]:
    """Passa cada fala rotulada pelo roteador real, `repetitions` vezes, e guarda o que ele decidiu.

    O nó do roteador trata uma falha do modelo em silêncio (segue "sem destinatário"), o que
    faria uma falha parecer um erro de acerto. Por isso a saída do nó é inspecionada, e a
    decisão vira `error` quando ele conta que falhou.

    O dono do assunto sai do evento `direction` do nó, que guarda o que o modelo respondeu.
    """
    results = []
    for case in cases:
        node = make_routing_node(contents[(case.scenario, case.level)], rng=NeutralDraw())
        for repetition in range(repetitions):
            state = {
                "messages": [*case.history, HumanMessage(content=case.line)],
                "current_speaker": case.current,
            }
            with captured_output() as output, collect_round_events() as events:
                decision = node(state)
            failed = _ROUTER_FAILURE_MARK in output.getvalue()
            if decision.get("addressed_by_student"):
                routed = decision.get("current_speaker", case.current)
            else:
                routed = NO_ADDRESSEE
            accepted = sorted(case.accepted) if case.accepted is not None else None
            topic_routed = _topic_owner(events)
            topic_accepted = sorted(case.topic) if case.topic is not None else None
            results.append(
                {
                    "id": case.id,
                    "scenario": case.scenario,
                    "kind": case.kind,
                    "current": case.current,
                    "line": case.line,
                    "accepted": accepted,
                    "repetition": repetition,
                    "routed": routed,
                    "correct": None if accepted is None else routed in accepted,
                    "topic_routed": topic_routed,
                    "topic_accepted": topic_accepted,
                    "topic_correct": (
                        None if topic_accepted is None else topic_routed in topic_accepted
                    ),
                    "error": output.getvalue().strip() if failed else "",
                }
            )
        progress(f"roteador: {case.id}")
    return results


def summarize_router(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Resume o acerto do roteador, separando as falas que chamam alguém das que só respondem.

    Os casos ambíguos e as decisões com falha ficam fora da conta, e os erros de acerto saem
    listados com a fala, o esperado e o obtido.
    """
    scored = [r for r in results if r["correct"] is not None and not r["error"]]
    named = [r for r in scored if r["kind"] == "named"]
    answers = [r for r in scored if r["kind"] == "answer"]
    topic = [r for r in results if r.get("topic_correct") is not None and not r["error"]]
    return {
        "topic_total": len(topic),
        "topic_correct": sum(1 for r in topic if r["topic_correct"]),
        "topic_errors": [r for r in topic if not r["topic_correct"]],
        "named_total": len(named),
        "named_correct": sum(1 for r in named if r["correct"]),
        "answer_total": len(answers),
        "answer_wrong": sum(1 for r in answers if not r["correct"]),
        "failed_calls": sum(1 for r in results if r["error"]),
        "ambiguous": [r for r in results if r["correct"] is None],
        "errors": [r for r in scored if not r["correct"]],
    }
