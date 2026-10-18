from pydantic import BaseModel, Field


class PersonaTurn(BaseModel):
    """Saída estruturada de um turno de persona: fala e roteamento da cena.

    Todo campo tem um default seguro: o modelo às vezes devolve uma chamada de
    ferramenta com campo ausente, e a falta de `line` já é tratada pelo chamador como
    um turno vazio a pular, não como erro.

    Não tem dica para o aluno: uma dica útil precisa dos critérios do cenário, que a
    persona não recebe, e pedir ao mesmo modelo, na mesma saída, o que o aluno deveria
    responder leva a persona a falar pelo aluno.

    `condition_met` vem antes da fala de propósito: a ordem dos campos é a ordem em que o
    modelo preenche a saída, então ele decide primeiro se o aluno já cumpriu o que faz o papel
    ceder e só depois escreve a fala. Medido com o modelo real, sem esse passo a persona que
    decide pedia mais detalhe do que o cartão exige e nunca concedia (0 de 6); com ele, 7 de
    8. O código não depende do campo: ele só ordena o raciocínio do modelo.
    """

    condition_met: bool = Field(
        default=False,
        description=(
            "Decide this FIRST. True when the student has already said, anywhere in the "
            "conversation, every part of what makes you concede (each part only once and in "
            "simple words). Only relevant if you decide the outcome; otherwise false"
        ),
    )
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
        description=(
            "True when you concede in this line, or when the student already got what they "
            "wanted from you"
        ),
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


class SuggestedAnswer(BaseModel):
    """Saída estruturada do tutor: a resposta que o aluno poderia dar, em português."""

    text: str = Field(
        default="",
        description=(
            "The answer the student could give, written in Portuguese, in the first person"
        ),
    )


class ReviewVerdict(BaseModel):
    """Saída estruturada do professor da revisão: o veredito de uma resposta falada.

    Os defaults descrevem uma resposta vazia, não um veredito: o serviço trata um feedback
    vazio como falha do provedor, e nunca como o aluno ter errado.
    """

    correct: bool = Field(
        default=False,
        description="True when the student's sentence satisfies the exercise of this step",
    )
    feedback: str = Field(
        default="",
        description=(
            "Short feedback for the student, in Brazilian Portuguese, at most two sentences"
        ),
    )
    correction: str = Field(
        default="",
        description=(
            "The student's sentence rewritten correctly in English, keeping what the "
            "student meant; empty when the sentence was correct"
        ),
    )


class ClosingLine(BaseModel):
    """Saída estruturada da fala de fechamento, quando os turnos se esgotam."""

    line: str = Field(default="", description="The character's final line, in English")


class ReviewItem(BaseModel):
    """Um erro de linguagem apontado pelo avaliador ao fim da execução.

    `rule` é a regra por trás do erro, e não o trecho: é ela que junta, num item de revisão
    só, erros iguais ditos com palavras diferentes em sessões diferentes. `produced` e
    `correct` são a frase inteira, com e sem o erro, e `note` é a nota em português que dá o
    contexto sem dar a resposta. `repeats` traz o identificador de uma regra que o aluno já
    tem quando o erro é a mesma regra, ou vazio.
    Todo campo tem default: um campo que o modelo deixou de preencher vira string vazia,
    nunca uma exceção.
    """

    rule: str = Field(
        default="",
        description=(
            "The general rule the student broke, short, in English "
            "(e.g. 'past simple with a finished time expression'), not the sentence"
        ),
    )
    produced: str = Field(
        default="",
        description="The WHOLE sentence the student said, with the mistake inside it",
    )
    correct: str = Field(
        default="",
        description="The same whole sentence corrected, keeping what the student meant",
    )
    note: str = Field(
        default="",
        description=(
            "One short sentence in Brazilian Portuguese telling the student what to look at "
            "in that sentence, never writing the correct English words"
        ),
    )
    repeats: str = Field(
        default="",
        description=(
            "The id of a KNOWN MISTAKE when this mistake breaks the same rule, "
            "otherwise empty"
        ),
    )


class DimensionScores(BaseModel):
    """Nota de cada dimensão julgada, uma propriedade nomeada por dimensão.

    Um dicionário de chaves abertas não serve aqui: no modo estrito de JSON schema o
    modelo só é obrigado a preencher propriedades que o schema nomeia, e devolvia o
    dicionário vazio. Os nomes dos campos são os valores de `RubricDimension`. Um campo
    sem nota fica `None`, para o avaliador distinguir "o modelo não julgou" de uma nota 0.
    """

    fluency: float | None = Field(default=None, description="Score from 0 up to the stated maximum")
    vocabulary: float | None = Field(
        default=None, description="Score from 0 up to the stated maximum"
    )
    grammar: float | None = Field(default=None, description="Score from 0 up to the stated maximum")
    pragmatics: float | None = Field(
        default=None, description="Score from 0 up to the stated maximum"
    )
    autonomy: float | None = Field(default=None, description="Score from 0 up to the stated maximum")


class EvaluationResult(BaseModel):
    """Saída estruturada do avaliador ao fim da execução de um cenário."""

    confirmed_criteria: list[str] = Field(
        default_factory=list, description="Ids of every acceptance criterion genuinely satisfied"
    )
    sub_scores: DimensionScores = Field(
        default_factory=DimensionScores,
        description="Score per judged dimension, up to its stated maximum",
    )
    feedback: str = Field(default="", description="2-3 sentences addressed to the student")
    memory_summary: str = Field(
        default="", description="3-4 short factual notes to remember for a future conversation"
    )
    review_items: list[ReviewItem] = Field(default_factory=list)
