import random

from apps.agents.graph.state import ScenarioState
from apps.agents.services.model_input import conversation_messages
from apps.agents.services.participation import scene_participation
from apps.agents.services.round_trace import record_round_event
from apps.agents.services.schemas import RoutingDecision
from apps.agents.services.scenario_content import ScenarioContent
from apps.agents.services.turn_balance import next_leader, should_hand_over
from apps.llm.constants import ModelPurpose
from apps.llm.services.factory import ModelNotConfigured, get_structured_llm

NO_ADDRESSEE = "none"

_ROUTING_PROMPT = """You direct a role-play conversation with {roster}. {leader} is leading now.

Look ONLY at the student's most recent message and answer two things.

1. "speaker": answer with a character's key ONLY if the student explicitly turns to that
character — calling them by name, or clearly speaking to them instead of to whoever asked
last. Simply answering the question that was just asked is NOT addressing anyone: answer
"{none}". A name used only to thank or greet someone ("Thanks, Rachel. I built REST
APIs...") is also NOT addressing them: it still answers the question that was just asked.
When the message names more than one character, answer with the key of the one who receives
the student's request or question, never the one who is only being thanked. Answer "{none}"
also whenever you are not sure.

2. "topic_owner": answer with the key of the character whose ROLE IN THE SCENE covers the
subject of the student's message. What each character is responsible for:
{areas}
Answer "{none}" when the subject is general, or when it fits {leader}, who is leading now.
What the student says to get what they want from {leader}, such as an argument, a request or
a proposal, is {leader}'s subject.

Answer each one with exactly one of: {valid_keys} | "{none}"."""


def make_routing_node(content: ScenarioContent, rng: random.Random | None = None):
    """Nó entre `listen` e `persona`: o diretor de cena, que decide quem conduz a rodada.

    Numa única chamada ao modelo de roteamento, ele responde duas coisas sobre a última fala
    do aluno: quem o aluno chamou e de quem é o assunto, pela função de cada papel na cena.
    A decisão vale nesta ordem, feita em código:

    1. O aluno chamou uma persona: é ela quem fala primeiro, mesmo que não fosse a vez dela, e
       `addressed_by_student` liga. Se o assunto é de outro personagem, `redirect_to` marca
       quem recebe a passagem de vez: a persona chamada diz que é com ele, e ele responde.
    2. Ninguém foi chamado, mas o assunto é de outro personagem que não o da vez: ele conduz a
       próxima parte da conversa, e o evento `topic_takeover` fica no registro. Medido com o
       modelo real, a persona nunca passava a vez por conta própria (0 das 20 trocas de 5
       sessões), então a passagem deixou de ser dela. Só assume pelo assunto quem decide o
       resultado da cena: medido na negociação, o motivo técnico dado à PM passava a rodada ao
       Tom em 2 de 3 amostras, e o aliado passava a interrogar o aluno em vez de apoiá-lo. O
       aliado continua entrando pelo equilíbrio e quando o aluno o chama.
    3. Sem chamado e sem assunto de outro: vale o equilíbrio. Se a persona da vez já conduziu
       rodadas seguidas demais, a conversa passa a outro personagem.

    Nas trocas dos itens 2 e 3 a rodada não é entregue direto a quem entra: a persona da vez
    continua sendo ela, e `hand_floor_to` marca quem recebe a palavra. Medido numa sessão real,
    entregar a rodada direto fazia a Emma reagir à resposta que o aluno deu ao James, e quem
    tinha perguntado parecia não ter ouvido. Com a marca, quem perguntou reage e passa a
    palavra pelo nome, e o colega pergunta em seguida, na mesma rodada.

    Sempre que reconhece um destinatário, liga `addressed_by_student`, inclusive quando
    ele já era a persona da vez: a persona chamada responde ao que o aluno disse e fecha
    a rodada, e sem essa marca ela não teria como saber que o aluno falou com ela. Esse caso
    não muda o estado da conversa, então ele é registrado no log: sem o registro, um
    equilíbrio de turnos que demora mais que o esperado não deixa saber se foi sorteio ou se
    a fala foi lida como dirigida à persona da vez.

    O prompt separa agradecer de chamar: medido com o modelo real, "Thanks, Rachel. I built
    REST APIs..." (resposta à pergunta do Tom) era lida como chamado à Rachel, e "Thanks for
    the support, Tom. Rachel, I need one more week." não era lida como chamado a ninguém. A
    pergunta do assunto manda responder "none" para o que o aluno diz para conseguir o que
    quer de quem conduz: o motivo técnico dado à PM faz parte da negociação dela e não passa a
    rodada ao tech lead.

    Sem modelo de roteamento configurado, ou se a chamada falhar por qualquer motivo, o
    nó trata como "sem destinatário e sem assunto" — o equilíbrio continua valendo, e a
    execução nunca é interrompida. `rng` é injetável para os testes controlarem o sorteio.
    """
    keys = content.role_keys()
    draw = rng or random.Random()

    def direction(state: ScenarioState, current: str) -> tuple[str | None, str | None]:
        roster = ", ".join(f"{content.role(key).name} (key: {key})" for key in keys)
        areas = "\n".join(
            f"- {content.role(key).name} (key: {key}): {content.role(key).scene_function}"
            for key in keys
        )
        system = _ROUTING_PROMPT.format(
            roster=roster,
            leader=content.role(current).name,
            areas=areas,
            none=NO_ADDRESSEE,
            valid_keys=" | ".join(f'"{key}"' for key in keys),
        )
        try:
            llm = get_structured_llm(ModelPurpose.ROUTER, RoutingDecision)
            decision = llm.invoke(conversation_messages(system, list(state["messages"])))
        except ModelNotConfigured:
            return None, None
        except Exception as exc:
            print(f"[routing] falha ao decidir roteamento, seguindo sem destinatario: {exc}")
            return None, None
        addressed = decision.speaker if decision.speaker in keys else None
        topic_owner = decision.topic_owner if decision.topic_owner in keys else None
        record_round_event(
            "direction",
            speaker=addressed or NO_ADDRESSEE,
            topic_owner=topic_owner or NO_ADDRESSEE,
            leader=current,
        )
        return addressed, topic_owner

    def node_routing(state: ScenarioState) -> dict:
        if len(keys) < 2:
            return {}

        current = state.get("current_speaker") or keys[0]
        addressed, topic_owner = direction(state, current)
        if addressed is not None:
            record_round_event("addressed", speaker=addressed, previous=current)
            redirect = topic_owner if topic_owner not in (None, addressed) else None
            marks = {"redirect_to": redirect} if redirect else {}
            if redirect:
                record_round_event("topic_redirect", speaker=addressed, target=redirect)
                print(
                    f"[routing] assunto de {content.role(redirect).name}; "
                    f"{content.role(addressed).name} passa a vez"
                )
            if addressed != current:
                print(f"[routing] aluno direcionou para {addressed} (era {current})")
                return {
                    "current_speaker": addressed,
                    "addressed_by_student": True,
                    **marks,
                }
            print(
                f"[routing] aluno falou com {content.role(current).name}; "
                "equilibrio de turno nao aplicado"
            )
            return {"addressed_by_student": True, **marks}

        if topic_owner is not None and topic_owner != current and content.decides(topic_owner):
            record_round_event("topic_takeover", speaker=topic_owner, previous=current)
            print(f"[routing] assunto de {content.role(topic_owner).name} (era {current})")
            return {"hand_floor_to": topic_owner}

        history = list(state["messages"])
        rounds_led = scene_participation(content, current, history).consecutive_rounds_led
        if should_hand_over(rounds_led, content.max_consecutive_turns, draw):
            leader = next_leader(content, current, history)
            record_round_event(
                "balance_takeover", leader=leader, previous=current, rounds_led=rounds_led
            )
            print(
                f"[routing] equilibrio: {current} conduziu {rounds_led} rodada(s) seguida(s); "
                f"vez de {leader}"
            )
            return {"hand_floor_to": leader}
        return {}

    return node_routing
