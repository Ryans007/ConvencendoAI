from rest_framework import serializers


class BriefingRoleSerializer(serializers.Serializer):
    """Uma persona do elenco, como aparece no briefing pré-sessão."""

    name = serializers.CharField(help_text="Nome da persona (ex.: 'Rachel').")
    scene_function = serializers.CharField(
        help_text="O que ela é na cena (ex.: 'recrutadora de RH')."
    )
    archetype = serializers.CharField(
        help_text="Papel interacional dela na cena (ex.: 'Gatekeeper', 'Aliado')."
    )


class ScenarioBriefingSerializer(serializers.Serializer):
    """Briefing pré-sessão de um cenário e nível: o que o aluno vê antes de começar.

    Nunca inclui os critérios de aceite nem os pesos da rubrica de avaliação — esses
    continuam ocultos até o relatório, depois que a sessão termina.
    """

    title = serializers.CharField(help_text="Título do cenário.")
    objective = serializers.CharField(help_text="O que o aluno precisa alcançar na conversa.")
    context = serializers.CharField(help_text="A situação em que o cenário se passa.")
    difficulty_label = serializers.CharField(help_text="Nome do nível (ex.: 'Conversa livre').")
    expected_cefr = serializers.CharField(
        help_text="Nível de proficiência esperado para este nível (ex.: 'A2-B1')."
    )
    max_turns = serializers.IntegerField(help_text="Quantos turnos de fala o aluno tem, no máximo.")
    roles = BriefingRoleSerializer(many=True, help_text="O elenco desta cena, na ordem de abertura.")
    memory_summary = serializers.CharField(
        allow_blank=True,
        help_text=(
            "Resumo do que as personas já sabem sobre o aluno, de uma tentativa aprovada "
            "anterior na mesma trilha — string vazia se não há tentativa anterior relevante."
        ),
    )
