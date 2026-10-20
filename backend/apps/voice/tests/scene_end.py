from apps.agents.graph import personas as graph_personas
from apps.catalog.models import Scenario


def end_after_the_first_turn(
    monkeypatch, line: str = "Deal, see you next week.", slug: str = "negociar-prazo", turns: int = 1
) -> None:
    """Faz a sessão do teste terminar pelo limite de turnos, que é como uma cena termina.

    Nenhuma persona decide o fim da cena, então um teste que precisa de uma sessão completa
    reduz o limite do cenário e substitui a fala de fechamento, que usaria um modelo de verdade.
    O limite vai direto ao banco: o mínimo de 7 turnos é uma validação do cadastro no admin.
    """
    Scenario.objects.filter(slug=slug).update(max_turns=turns)
    monkeypatch.setattr(graph_personas, "generate_closing_line", lambda content, role, history: line)
