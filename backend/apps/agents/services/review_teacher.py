import re

from langchain_core.messages import HumanMessage

from apps.agents.services.language import looks_english
from apps.agents.services.schemas import ReviewVerdict
from apps.llm.constants import ModelPurpose
from apps.llm.services.factory import get_structured_llm

MAX_TRIES = 3
STEP_NEW_SENTENCE = 2

_PROMPT = """You are an English teacher reviewing ONE spoken sentence from a Brazilian
student who is practising spoken English. You only get a text transcription of what
the student said, never the audio: ignore capitalization, punctuation and anything that
looks like a transcription artifact, and NEVER comment on pronunciation or accent.

THE RULE THE STUDENT GOT WRONG IN A PREVIOUS CONVERSATION
{rule}
What the student said then: "{said}"
The correct form: "{correct}"

{note_block}THE EXERCISE
{exercise}

WHAT THE STUDENT SAID NOW (attempt {attempt} of 2): "{heard}"

HOW TO ANSWER
- correct: true only if the sentence satisfies the exercise above.
- feedback: written in Brazilian Portuguese, at most TWO short sentences, and never in
  English (English words that are part of the example are fine).
{feedback_rules}
- correction: when correct is false, the student's own sentence rewritten correctly in
  English, keeping what the student meant. Empty when correct is true."""

_NOTE_BLOCK = """ALREADY SHOWN TO THE STUDENT
Before answering, the student read this note about the mistake: "{note}"
Do not repeat it. When you give a hint, look at the mistake from another angle.

"""

_EXERCISE_REPEAT = """Step 1. The student had to say the sentence again, corrected. Mark it
correct when the sentence fixes the mistake of the rule above, even with different words,
a different word order or small variations. Other mistakes that have nothing to do with
the rule above must NOT make the sentence wrong."""

_EXERCISE_NEW = """Step 2. The student had to say a NEW sentence, on any topic, that applies the SAME
RULE as above. The rule is what matters, never the wording of the example: do not require
the sentence to follow the example's word order, its template or its other words. Mark it
correct when the sentence uses the point of the rule correctly (for a word-choice rule,
the right word where it belongs; for a grammar rule, the grammar done correctly), even if
the rest of the sentence is different, longer or on a different topic. Mark it wrong only
when the sentence breaks the rule, or does not use the point of the rule at all."""

_FEEDBACK_IF_CORRECT = (
    "- If the sentence is correct: confirm in one short sentence why it is right, naming "
    "the rule in simple words."
)
_FEEDBACK_IF_WRONG_FIRST = (
    "- If the sentence is wrong, this is the FIRST attempt: give a HINT only, telling what "
    'to look at (for example "Repare em yesterday: ele marca um tempo que já terminou"). '
    "NEVER write the correct sentence, or the words that fix the sentence."
)
_FEEDBACK_IF_WRONG_LAST = (
    "- If the sentence is wrong, this is the LAST attempt: explain the rule in simple words "
    "and what went wrong in the student's sentence."
)

_FIRST_MISS_WITH_NOTE = "Ainda não. Releia o contexto acima e tente de novo."
_REPEATED_SENTENCE_FEEDBACK = (
    "Essa é a mesma frase da etapa anterior. Diga uma frase nova, de outro assunto, "
    "com a mesma estrutura."
)
_FALLBACK_CORRECT = "Certo. Sua frase usa a regra corretamente."
_FALLBACK_FIRST_MISS = "Ainda não. Releia a regra desta frase e tente de novo."
_FALLBACK_LAST_MISS = "Não foi desta vez. Vale rever a regra desta frase com a forma correta."
_NON_WORD = re.compile(r"[^a-z0-9' ]+")
_QUOTED_EXAMPLE = re.compile(r"""(?<!\w)'[^']*'(?!\w)|"[^"]*"|“[^”]*”|‘[^’]*’|«[^»]*»""")
_FORMULA = re.compile(r"\S+(?:\s*\+\s*\S+)+")


class ReviewJudgmentFailed(RuntimeError):
    """O professor não devolveu um veredito utilizável, por exemplo uma saída vazia.

    É uma falha do serviço, e não um erro do aluno: quem chama deve deixar o aluno tentar
    de novo sem gastar a tentativa.
    """


def _without_examples(text: str) -> str:
    """O feedback sem os exemplos em inglês que ele cita, para medir só a língua do texto.

    O professor explica em português mas cita a regra e as frases em inglês, entre aspas ou
    como "need + person + to + verb". Contar essas palavras faria um feedback certo parecer
    inglês e pediria o veredito de novo à toa.
    """
    return _FORMULA.sub(" ", _QUOTED_EXAMPLE.sub(" ", text))


def _normalize(text: str) -> str:
    return " ".join(_NON_WORD.sub(" ", text.lower().replace("’", "'")).split())


def _build_prompt(
    *, rule: str, said: str, correct: str, note: str, step: int, attempt: int, heard: str
) -> str:
    first_miss = attempt == 1
    wrong_rule = _FEEDBACK_IF_WRONG_FIRST if first_miss else _FEEDBACK_IF_WRONG_LAST
    return _PROMPT.format(
        rule=rule,
        said=said,
        correct=correct,
        note_block=_NOTE_BLOCK.format(note=note.strip()) if note.strip() else "",
        exercise=_EXERCISE_NEW if step == STEP_NEW_SENTENCE else _EXERCISE_REPEAT,
        attempt=attempt,
        heard=heard,
        feedback_rules=f"{_FEEDBACK_IF_CORRECT}\n{wrong_rule}",
    )


def _is_acceptable(verdict: ReviewVerdict, attempt: int, correct_form: str) -> bool:
    """O feedback está em português e, num primeiro erro, não entrega a forma correta."""
    feedback = verdict.feedback.strip()
    if not feedback or looks_english(_without_examples(feedback)):
        return False
    gives_the_answer = _normalize(correct_form) in _normalize(feedback)
    return not (not verdict.correct and attempt == 1 and gives_the_answer)


def _generic_feedback(verdict: ReviewVerdict, attempt: int) -> str:
    if verdict.correct:
        return _FALLBACK_CORRECT
    return _FALLBACK_FIRST_MISS if attempt == 1 else _FALLBACK_LAST_MISS


def judge_review_answer(
    *, rule: str, said: str, correct: str, note: str = "", step: int, attempt: int, heard: str
) -> ReviewVerdict:
    """O professor julga uma resposta falada da revisão, em português, para o aluno.

    Usa o modelo do avaliador, o mesmo que decide se o aluno errou a regra na sessão. Na
    etapa 2, repetir a forma correta da etapa 1 é recusado sem chamar o modelo, porque
    nada de novo foi dito e a frase é conhecida de antemão. Duas proteções em código cobrem
    o que só a instrução não garantiu: um feedback que sai em inglês, e uma pista de
    primeiro erro que contém a forma correta inteira. Cada uma pede o veredito de novo, até
    `MAX_TRIES` vezes; esgotadas as chamadas, o veredito segue com um feedback genérico em
    português. Uma saída vazia do provedor, que o cliente de LLM devolve como o schema sem
    preencher, vira `ReviewJudgmentFailed`: julgar o aluno errado por causa disso seria
    injusto.

    Quando o veredito é errado mas a correção do modelo é a própria frase do aluno, só com
    pontuação ou maiúscula diferentes, a correção vira a forma correta do item: mostrar a
    frase dele como "forma correta" não ensina nada e confunde.

    A nota em português que o cartão já mostrou entra no prompt. No primeiro erro de um item
    com nota, o feedback é uma frase fixa que remete a ela: medido com o modelo real, pedir à
    IA um "outro ângulo" não funcionava (repetia a nota em 6 de 6, e com uma instrução mais
    forte passou a escrever o inglês correto), e o contexto já está na tela.
    """
    if step == STEP_NEW_SENTENCE and _normalize(heard) == _normalize(correct):
        return ReviewVerdict(
            correct=False, feedback=_REPEATED_SENTENCE_FEEDBACK, correction=correct
        )

    verdict = _judge(
        rule=rule, said=said, correct=correct, note=note, step=step, attempt=attempt, heard=heard
    )
    if not verdict.correct and _normalize(verdict.correction) == _normalize(heard):
        return verdict.model_copy(update={"correction": correct})
    return verdict


def _judge(
    *, rule: str, said: str, correct: str, note: str, step: int, attempt: int, heard: str
) -> ReviewVerdict:
    """Pede o veredito ao modelo, com as proteções de idioma e de pista, e o devolve."""
    prompt = _build_prompt(
        rule=rule,
        said=said,
        correct=correct,
        note=note,
        step=step,
        attempt=attempt,
        heard=heard,
    )
    llm = get_structured_llm(ModelPurpose.JUDGE, ReviewVerdict)
    verdict = ReviewVerdict()
    for _ in range(MAX_TRIES):
        verdict = llm.invoke([HumanMessage(content=prompt)])
        if verdict.feedback.strip() and note.strip() and attempt == 1 and not verdict.correct:
            return verdict.model_copy(update={"feedback": _FIRST_MISS_WITH_NOTE})
        if _is_acceptable(verdict, attempt, correct):
            return verdict
        print(f"[review] feedback descartado: {verdict.feedback!r}")

    if not verdict.feedback.strip():
        raise ReviewJudgmentFailed("o professor devolveu um veredito vazio")
    return verdict.model_copy(update={"feedback": _generic_feedback(verdict, attempt)})
