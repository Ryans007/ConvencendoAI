from collections.abc import Callable
from typing import Any

from apps.agents.evaluation.schemas import ROLE_ITEMS, RoleVerdict
from apps.llm.constants import ModelPurpose

MODULES = (
    "apps.agents.graph.personas",
    "apps.agents.graph.routing",
    "apps.agents.services.personas",
    "apps.agents.evaluation.judge",
    "apps.agents.evaluation.simulated_student",
)


class _Agent:
    def __init__(self, handler: Callable[[list], Any]):
        self._handler = handler

    def invoke(self, messages: list) -> Any:
        return self._handler(messages)


class FakeModels:
    """Substitui `get_structured_llm` por respostas roteirizadas, sem nenhuma chamada a provedor.

    Cada resposta é escolhida pelo papel e pelo nome do schema pedido. Um valor pode ser um
    objeto (devolvido sempre), uma lista (devolvida em ordem, repetindo a última) ou uma função
    que recebe as mensagens e devolve o objeto, para a resposta depender do que foi perguntado.
    """

    def __init__(self) -> None:
        self._answers: dict[tuple[str, str], Any] = {}
        self.calls: list[tuple[str, str]] = []

    def set(self, purpose: str, schema_name: str, answer: Any) -> None:
        self._answers[(purpose, schema_name)] = answer

    def install(self, monkeypatch) -> "FakeModels":
        for module in MODULES:
            monkeypatch.setattr(f"{module}.get_structured_llm", self, raising=True)
        return self

    def __call__(self, purpose: str, schema: type) -> _Agent:
        key = (purpose, schema.__name__)
        self.calls.append(key)
        if key not in self._answers:
            raise AssertionError(f"Resposta falsa não definida para {key}.")
        answer = self._answers[key]
        if callable(answer):
            return _Agent(answer)
        if isinstance(answer, list):
            queue = answer

            def next_answer(messages: list) -> Any:
                return queue.pop(0) if len(queue) > 1 else queue[0]

            return _Agent(next_answer)
        return _Agent(lambda messages: answer)


def role_verdict(**answers: str):
    """Veredito do juiz: tudo `yes`, exceto os itens dados (`item="no"`)."""
    fields: dict[str, str] = {}
    for item in ROLE_ITEMS:
        fields[item] = answers.get(item, "yes")
        fields[f"{item}_reason"] = answers.get(f"{item}_reason", f"{item} ok")
    return RoleVerdict(**fields)


PERSONA = ModelPurpose.PERSONA
ROUTER = ModelPurpose.ROUTER
JUDGE = ModelPurpose.JUDGE
