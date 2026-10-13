from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from apps.agents.evaluation.case_loader import StudentProfile
from apps.agents.evaluation.schemas import StudentReply
from apps.agents.services.round_trace import record_round_event
from apps.agents.services.scenario_content import ScenarioContent
from apps.agents.services.transcript import transcript_text
from apps.llm.constants import ModelPurpose
from apps.llm.services.factory import get_structured_llm

FALLBACK_REPLY = "Sorry, can you repeat?"

_PROMPT = """You are role-playing a Brazilian learner of English in a speaking-practice simulation.
Stay in the learner's role the whole time.

SITUATION (from the learner's point of view): {context}
YOUR GOAL: {objective}
THE PEOPLE TALKING TO YOU: {people}

YOUR ENGLISH: {english}
YOUR PROFILE: {profile}
{beat}
Write ONLY what you say next: {length}. Never write the other people's lines, never narrate,
never mention that this is a simulation, and never use Portuguese."""


class SimulatedStudent:
    """O aluno que conversa com o grafo numa sessão avaliada, gerado pelo modelo do avaliador.

    Segue um perfil (objetivo, nível de inglês e tamanho das respostas) e, em falas
    escolhidas, uma instrução pontual: chamar alguém pelo nome, agradecer, pedir algo que a
    cena não oferece. Assim a sessão passa pelos caminhos de troca de vez sem depender da sorte.
    """

    def __init__(self, content: ScenarioContent, profile: StudentProfile):
        self._content = content
        self._profile = profile
        self._people = "; ".join(f"{role.name} ({role.scene_function})" for role in content.roles)

    def system_prompt(self, reply_number: int) -> str:
        """O prompt da fala `reply_number` (a partir de 1), com a instrução dela, se houver."""
        instruction = self._profile.beats.get(reply_number, "")
        return _PROMPT.format(
            context=self._content.context,
            objective=self._content.objective,
            people=self._people,
            english=self._profile.english,
            profile=self._profile.profile,
            beat=f"\nINSTRUCTION FOR THIS REPLY: {instruction}\n" if instruction else "",
            length=self._profile.length,
        )

    def listen(self, state: dict[str, Any]) -> dict[str, Any]:
        """Nó `listen` do grafo: pede a próxima fala ao modelo, em vez de esperar a voz do aluno."""
        messages = list(state["messages"])
        reply_number = sum(isinstance(message, HumanMessage) for message in messages) + 1
        body = (
            f"CONVERSATION SO FAR\n{transcript_text(messages)}\n\nWhat do you say next?"
        )
        llm = get_structured_llm(ModelPurpose.JUDGE, StudentReply)
        line = ""
        for _ in range(3):
            system = SystemMessage(content=self.system_prompt(reply_number))
            reply = llm.invoke([system, HumanMessage(content=body)])
            line = (reply.line or "").strip()
            if line:
                break
        record_round_event("student_turn", number=reply_number)
        return {
            "messages": [HumanMessage(content=line or FALLBACK_REPLY)],
            "turn_count": state.get("turn_count", 0) + 1,
        }
