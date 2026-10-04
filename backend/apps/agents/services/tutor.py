import re

from langchain_core.messages import HumanMessage

from apps.agents.services.scenario_content import ScenarioContent
from apps.agents.services.schemas import SuggestedAnswer
from apps.agents.services.transcript import transcript_text
from apps.llm.constants import ModelPurpose
from apps.llm.services.factory import get_structured_llm

_PROMPT = """You help a Brazilian student who is practising spoken English in a
role-play. The student asked for help to answer the character's last line. Write, in
PORTUGUESE, an answer the student could give: in the first person, as the student
speaking. The student will say it in English themselves, and that is their exercise,
so you never write English for them.

THE SCENE
{context}
What the student wants in this scene: {objective}

WHAT THIS LEVEL ASKS OF THE STUDENT ({difficulty})
"{expected_production}"
The student has to say your answer in English, so keep it short enough to say. Match
it to the level:
- closed answers (yes/no or a choice): "sim" or "não", or the chosen option, plus at
  most a few words. At most 6 words. Add no details nobody asked for.
- short sentences: ONE short sentence. At most 15 words.
- free conversation: at most TWO sentences, with one concrete detail. At most 30 words.

WHAT THE STUDENT SHOULD SHOW IN THIS SCENE (private: never mention it to the student)
{criteria}
Read the conversation. Pick AT MOST ONE item above that the student has not shown yet
and that fits the character's last line, and let your answer cover it: for example, a
concrete example when they were asked about their experience. Cover nothing that the
line does not ask about: never add a question of your own unless the character invited
the student to ask something, and never pack several items into one answer.

CONVERSATION SO FAR
{transcript}

RULES
- Answer the character's LAST line, the one the student must respond to now.
- Portuguese only. No English words or sentences, except names of people, companies,
  products and technologies. Translate the options the character offered too: "web
  app" becomes "aplicativo web".
- Keep facts simple: no percentages, statistics or dates that the conversation does
  not already have.
- First person, as the student: "Sim, trabalhei em equipe.", never "Diga que...".
- Stay consistent with everything the student already said. Never contradict it, and
  reuse their own facts (project, role, tools) when they fit.
- Never mention criteria, evaluation, score, passing, or what the student must do.
- Write only the answer, nothing before or after it."""


_ENGLISH_MARKERS = frozenset(
    "the i we is are was were be been have has had need needs could would will which my "
    "our it its this that these those to of and for with by from at what can".split()
)
_PORTUGUESE_MARKERS = frozenset(
    "o a os as de do da dos das que e é em no na um uma para com não sim eu nós meu minha "
    "foi era porque mais isso esse essa por se já".split()
)
_WORD = re.compile(r"[a-zà-ú]+")


def looks_english(text: str) -> bool:
    """A sugestão parece escrita em inglês, e não em português?

    Conta palavras típicas de cada língua e decide pela que aparece mais. Nomes de
    tecnologias e de produtos não entram em nenhuma das duas listas, então uma sugestão em
    português cheia de nomes técnicos continua sendo português.
    """
    words = _WORD.findall(text.lower())
    english = sum(word in _ENGLISH_MARKERS for word in words)
    portuguese = sum(word in _PORTUGUESE_MARKERS for word in words)
    return english > portuguese


def suggest_answer(content: ScenarioContent, history: list) -> str:
    """Escreve a dica do aluno: o que ele poderia responder à fala atual, em português.

    É uma chamada própria, fora do papel da persona, porque a dica precisa dos critérios
    do cenário — que a persona não recebe, para não virar professora — e porque só deve
    custar alguma coisa quando o aluno pede. Usa o modelo da persona. A sugestão
    encaminha para o que o aluno ainda não mostrou, sem nunca dizer que existe um
    critério, e não traz inglês: dizer em inglês é o exercício do aluno. Medido com o
    modelo real, a instrução sozinha não bastava: uma sugestão em 20 veio inteira em
    inglês, entregando a resposta pronta. Por isso uma sugestão que parece inglês é
    descartada como uma vazia. Devolve texto vazio quando nenhuma das duas tentativas
    produz uma sugestão em português.
    """
    criteria = "\n".join(f"- {criterion.text}" for criterion in content.criteria) or "- (none)"
    prompt = _PROMPT.format(
        context=content.context,
        objective=content.objective,
        difficulty=content.difficulty_label,
        expected_production=content.expected_production,
        criteria=criteria,
        transcript=transcript_text(history),
    )
    llm = get_structured_llm(ModelPurpose.PERSONA, SuggestedAnswer)

    for _ in range(2):
        text = (llm.invoke([HumanMessage(content=prompt)]).text or "").strip()
        if text and not looks_english(text):
            return text
        if text:
            print(f"[hint] sugestão em inglês descartada: {text}")
    return ""
