from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_events: ContextVar[list[dict[str, Any]] | None] = ContextVar("round_events", default=None)


@contextmanager
def collect_round_events() -> Iterator[list[dict[str, Any]]]:
    """Coleta, dentro do bloco, os eventos estruturados de cada rodada da conversa.

    Os nós do grafo (abertura, roteamento e persona) registram o que decidiram — quem o aluno
    chamou, a troca pelo equilíbrio, a passagem de vez, o fechamento —, e a avaliação da conversa
    calcula as métricas de troca a partir deles, sem depender da redação do log. A coleta é uma
    variável de contexto, o mesmo mecanismo do dono do uso: a lista é compartilhada por
    referência, então os eventos registrados nas threads do grafo chegam a ela.
    """
    events: list[dict[str, Any]] = []
    token = _events.set(events)
    try:
        yield events
    finally:
        _events.reset(token)


def record_round_event(kind: str, **data: Any) -> None:
    """Registra um evento da rodada. Fora de uma coleta não faz nada: a sessão real não muda."""
    events = _events.get()
    if events is not None:
        events.append({"kind": kind, **data})
