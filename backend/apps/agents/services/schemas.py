from pydantic import BaseModel, Field


class PersonaTurn(BaseModel):
    """Saída estruturada de um turno de persona: fala, dica e roteamento da cena.

    Todo campo tem um default seguro: o modelo às vezes devolve uma chamada de
    ferramenta com campo ausente, e a falta de `line` já é tratada pelo chamador como
    um turno vazio a pular, não como erro.
    """

    line: str = Field(default="", description="The character's spoken line, in English")
    hint: str = Field(default="", description="Short hint for the student, in Portuguese")
    pass_to: str = Field(
        default="student",
        description=(
            "Who should respond to this line: \"student\" if it is addressed to the "
            "student, or the key of the other character if THEY should respond right "
            "now, in this same turn, because this line was addressed to them instead"
        ),
    )
    scene_resolved: bool = Field(
        default=False,
        description="True only when the student already got what they wanted from you",
    )


class RoutingDecision(BaseModel):
    """Saída estruturada do roteador: qual persona deve responder ao aluno agora."""

    speaker: str = Field(
        default="",
        description=(
            "Key of the character who should respond to the student's last message"
        ),
    )


class ClosingLine(BaseModel):
    """Saída estruturada da fala de fechamento, quando os turnos se esgotam."""

    line: str = Field(default="", description="The character's final line, in English")


class ClosingHintTurn(BaseModel):
    """Saída estruturada da fala que abre a oportunidade dos critérios de aceite."""

    line: str = Field(default="", description="The character's line, in English")
    hint: str = Field(default="", description="Short hint for the student, in Portuguese")


class ReviewItem(BaseModel):
    """Um item de erro de linguagem extraído pelo avaliador ao fim da execução.

    Nunca é persistido — ver `EvaluationResult.review_items` — então um campo que o
    modelo deixou de preencher vira string vazia, nunca uma exceção.
    """

    item: str = Field(
        default="", description="The language item being reviewed (word, structure or sound)"
    )
    produced: str = Field(default="", description="The form the student actually produced")
    correct: str = Field(default="", description="The correct form")


class EvaluationResult(BaseModel):
    """Saída estruturada do avaliador ao fim da execução de um cenário."""

    confirmed_criteria: list[str] = Field(
        default_factory=list, description="Ids of every acceptance criterion genuinely satisfied"
    )
    sub_scores: dict[str, float] = Field(
        default_factory=dict, description="Score per judged dimension, up to its stated maximum"
    )
    feedback: str = Field(default="", description="2-3 sentences addressed to the student")
    memory_summary: str = Field(
        default="", description="3-4 short factual notes to remember for a future conversation"
    )
    review_items: list[ReviewItem] = Field(default_factory=list)
