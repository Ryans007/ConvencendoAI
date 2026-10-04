from pydantic import BaseModel, Field


class PersonaTurn(BaseModel):
    """Saída estruturada de um turno de persona: fala e roteamento da cena.

    Todo campo tem um default seguro: o modelo às vezes devolve uma chamada de
    ferramenta com campo ausente, e a falta de `line` já é tratada pelo chamador como
    um turno vazio a pular, não como erro.

    Não tem dica para o aluno: uma dica útil precisa dos critérios do cenário, que a
    persona não recebe, e pedir ao mesmo modelo, na mesma saída, o que o aluno deveria
    responder leva a persona a falar pelo aluno.
    """

    line: str = Field(default="", description="The character's spoken line, in English")
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
    """Saída estruturada do roteador: a qual persona o aluno se dirigiu, se a alguma.

    `"none"` quando o aluno não se dirige a ninguém em especial: separar esse caso de "o
    aluno chamou a persona atual" é o que permite ao equilíbrio de turno valer só quando
    a escolha não foi do aluno.
    """

    speaker: str = Field(
        default="none",
        description=(
            "Key of the character the student's last message clearly addresses, "
            'or "none" if it does not address one specific character'
        ),
    )


class ClosingLine(BaseModel):
    """Saída estruturada da fala de fechamento, quando os turnos se esgotam."""

    line: str = Field(default="", description="The character's final line, in English")


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
