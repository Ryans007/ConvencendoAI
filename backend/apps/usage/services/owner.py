from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class UsageOwner:
    """Quem originou as chamadas a modelo desta execução: o aluno e a sessão ou o item."""

    user_id: int | None
    username: str
    attempt_id: int | None
    review_item_id: int | None


_current: ContextVar[UsageOwner | None] = ContextVar("usage_owner", default=None)


@contextmanager
def usage_owner(*, user=None, attempt=None, review_item=None, label="") -> Iterator[UsageOwner]:
    """Marca, dentro do bloco, o dono das chamadas a modelo, para a gravação do uso.

    A marca é uma variável de contexto: o `sync_to_async` e o executor do LangGraph copiam o
    contexto para a thread em que o modelo é chamado, então as chamadas feitas lá embaixo
    enxergam o dono sem que cada uma o receba por parâmetro. Guarda só os ids e o nome, e não
    os objetos, para a marca atravessar threads sem carregar consultas pendentes. Fora do
    bloco não há marca, e a chamada fica como uso do sistema. Sem aluno, o `label` vira o nome
    gravado no uso, para distinguir o uso de uma rotina conhecida (como a avaliação da conversa)
    do uso do sistema sem nome.
    """
    owner = UsageOwner(
        user_id=user.pk if user is not None else None,
        username=user.get_username() if user is not None else label,
        attempt_id=attempt.pk if attempt is not None else None,
        review_item_id=review_item.pk if review_item is not None else None,
    )
    token = _current.set(owner)
    try:
        yield owner
    finally:
        _current.reset(token)


def current_owner() -> UsageOwner | None:
    """O dono marcado para a execução em curso, ou `None` fora de uma marca."""
    return _current.get()
