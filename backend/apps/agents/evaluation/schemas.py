from typing import Literal

from pydantic import BaseModel, Field, create_model

ROLE_ITEMS: dict[str, tuple[str, str]] = {
    "stays_in_function": (
        "Fica na função",
        "Does the line stay within the character's function in this scene, without taking over "
        "the area of another character?",
    ),
    "acts_as_archetype": (
        "Age como o arquétipo",
        "Does the line behave like the character's archetype, as described in the character card?",
    ),
    "only_scene_facts": (
        "Só usa fatos da cena",
        "Does the line state only facts present in the scene description, in the character's "
        "facts, or already said by the student earlier in the conversation, without inventing "
        "facts, offers, policies, numbers or dates? A fact the student just said, repeated or "
        "reacted to by the character, is not invented. Use na when the line states no facts.",
    ),
    "no_english_correction": (
        "Não corrige o inglês",
        "Does the line avoid correcting, grading or commenting on the student's English?",
    ),
    "answers_student_first": (
        "Responde ao aluno primeiro",
        "If the student's last message asked this character something or made a comment to "
        "them, does the line start by answering or reacting to it? Use na when it did not.",
    ),
    "no_repeated_question": (
        "Não repete pergunta",
        "Does the line avoid asking something that was already asked, or already answered by "
        "the student, earlier in the conversation?",
    ),
    "at_most_one_question": (
        "No máximo uma pergunta",
        "Does the line contain at most one question to the student?",
    ),
    "english_only": ("Só inglês", "Is the line written only in English?"),
    "no_task_reveal": (
        "Não entrega a tarefa",
        "Does the line avoid telling the student what they must say or do to succeed?",
    ),
    "supporting_stays_brief": (
        "Coadjuvante não conduz",
        "If this character is a supporting character, does the line stay brief (at most two "
        "short sentences), avoid leading the scene, and contain a question to the student only "
        "when the line closes the round? Use na when the character is not a supporting "
        "character.",
    ),
}

Answer = Literal["yes", "no", "na"]


def _build_role_verdict() -> type[BaseModel]:
    fields: dict = {}
    for item, (_, question) in ROLE_ITEMS.items():
        fields[item] = (
            Answer,
            Field(default="na", description=f"{question} Answer yes, no or na (not applicable)."),
        )
        fields[f"{item}_reason"] = (
            str,
            Field(
                default="",
                description="One short sentence, in Brazilian Portuguese, justifying the answer.",
            ),
        )
    return create_model(
        "RoleVerdict",
        __doc__="Veredito do juiz sobre uma fala de persona: cada item da lista de verificação.",
        **fields,
    )


RoleVerdict = _build_role_verdict()


class SemanticVerdict(BaseModel):
    """Veredito do juiz sobre uma pergunta de sim ou não escrita no próprio caso."""

    answer: Literal["yes", "no"] = Field(
        default="no", description="yes if the statement in the question is true for the line(s)"
    )
    reason: str = Field(
        default="",
        description="One short sentence, in Brazilian Portuguese, that justifies the answer.",
    )


class StudentReply(BaseModel):
    """O que o aluno simulado diz a seguir."""

    line: str = Field(default="", description="What the learner says next, in English")
