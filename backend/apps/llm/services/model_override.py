from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar

from apps.llm.constants import ModelCategory, ModelPurpose
from apps.llm.models import LLMModel

_current: ContextVar[Mapping[str, LLMModel] | None] = ContextVar("model_override", default=None)


@contextmanager
def override_models(models: Mapping[str, LLMModel]) -> Iterator[None]:
    """Usa outro modelo cadastrado para um papel de chat, só dentro do bloco.

    A escolha é uma variável de contexto, como o dono do uso: vale nas threads abertas pelo
    bloco e não altera a configuração gravada, então uma sessão real que acontece ao mesmo
    tempo continua com o modelo da configuração. Serve para comparar modelos numa avaliação sem
    mexer no que os alunos usam. Só modelos de chat servem aos papéis de chat; as demais
    verificações (modelo e provedor ativos, chave no ambiente) são as do caminho normal, feitas
    quando a chamada é montada.
    """
    valid_purposes = {purpose.value for purpose in ModelPurpose}
    for purpose, model in models.items():
        if purpose not in valid_purposes:
            raise ValueError(f"Papel desconhecido para troca de modelo: '{purpose}'.")
        if model.category != ModelCategory.CHAT:
            raise ValueError(
                f"O modelo '{model.model_id}' é de '{model.category}' e não serve ao papel "
                f"'{purpose}', que usa um modelo de chat."
            )
    token = _current.set(dict(models))
    try:
        yield
    finally:
        _current.reset(token)


def current_override(purpose: str) -> LLMModel | None:
    """O modelo escolhido para o papel no bloco em curso, ou `None` fora de uma troca."""
    chosen = _current.get()
    return chosen.get(purpose) if chosen else None
