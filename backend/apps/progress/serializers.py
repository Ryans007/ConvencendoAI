from rest_framework import serializers


class LastAttemptSerializer(serializers.Serializer):
    """Resumo da última tentativa concluída de um nível, para a jornada do aluno."""

    id = serializers.IntegerField(help_text="Identificador da tentativa, que abre o relatório.")
    final_score = serializers.IntegerField(help_text="Nota final da tentativa, de 0 a 100.")
    passed = serializers.BooleanField(help_text="A tentativa atingiu a nota mínima.")
    completed_at = serializers.DateTimeField(help_text="Quando a tentativa foi concluída.")


class LevelStateSerializer(serializers.Serializer):
    """Estado calculado de um nível dentro de um cenário, para a jornada do aluno."""

    order = serializers.IntegerField(source="level.order", help_text="Ordem do nível (1 a 3).")
    name = serializers.CharField(source="level.name")
    expected_cefr = serializers.CharField(
        source="level.expected_cefr", help_text="Nível de proficiência esperado (ex.: 'A2-B1')."
    )
    approved = serializers.BooleanField(
        help_text="Já existe alguma tentativa aprovada do aluno neste cenário e nível."
    )
    available = serializers.BooleanField(
        help_text="Não está em cooldown — pode ser tentado agora, aprovado ou não antes."
    )
    cooldown_remaining_seconds = serializers.SerializerMethodField(
        help_text="Segundos até liberar de novo, ou nulo se já está disponível."
    )
    last_attempt = LastAttemptSerializer(
        allow_null=True,
        help_text=(
            "Tentativa concluída mais recente neste cenário e nível, aprovada ou não, ou "
            "nulo se o aluno nunca concluiu uma."
        ),
    )

    def get_cooldown_remaining_seconds(self, obj) -> int | None:
        if obj.cooldown_remaining is None:
            return None
        return int(obj.cooldown_remaining.total_seconds())


class ScenarioStateSerializer(serializers.Serializer):
    """Estado calculado de um cenário, para a jornada do aluno."""

    slug = serializers.CharField(source="scenario.slug")
    title = serializers.CharField(source="scenario.title")
    order = serializers.IntegerField(source="scenario.order")
    completed = serializers.BooleanField(
        help_text="O aluno já tem alguma tentativa aprovada neste cenário, em qualquer nível."
    )
    unlocked = serializers.BooleanField(
        help_text="A trilha está liberada e o cenário anterior, se houver, já está concluído."
    )
    level_states = LevelStateSerializer(many=True)


class ScoreBreakdownSerializer(serializers.Serializer):
    """Sub-nota de uma dimensão numa tentativa, com o peso que valia no momento."""

    dimension = serializers.CharField(
        help_text=(
            "Uma das sete dimensões da rubrica: objective, fluency, vocabulary, grammar, "
            "pronunciation, pragmatics, autonomy."
        )
    )
    value = serializers.IntegerField(help_text="Pontos obtidos nesta dimensão.")
    weight = serializers.IntegerField(
        source="weight_at_time",
        help_text="Peso máximo da dimensão no momento da tentativa (histórico, não muda depois).",
    )


class AttemptCriterionSerializer(serializers.Serializer):
    """Resultado de um critério avaliado numa tentativa."""

    code = serializers.CharField(help_text="Identificador curto do critério dentro do cenário.")
    text = serializers.CharField(
        source="text_at_time",
        help_text="Texto do critério como estava redigido no momento da tentativa.",
    )
    met = serializers.BooleanField(help_text="Se o aluno cumpriu este critério nesta tentativa.")


class AttemptReportSerializer(serializers.Serializer):
    """Relatório completo de uma tentativa já concluída: nota final, sub-nota por
    dimensão, resultado de cada critério aplicável, e o feedback do avaliador.
    """

    id = serializers.IntegerField()
    scenario = serializers.CharField(source="scenario.slug")
    level = serializers.IntegerField(source="level.order")
    final_score = serializers.IntegerField(help_text="Nota de 0 a 100, normalizada sobre o peso avaliado.")
    passed = serializers.BooleanField(help_text="Se a nota atingiu o mínimo de aprovação.")
    feedback = serializers.CharField(help_text="2-3 frases do avaliador sobre o desempenho.")
    completed_at = serializers.DateTimeField()
    hints_enabled = serializers.BooleanField(
        help_text="O aluno começou a sessão com as dicas ligadas."
    )
    hints_used = serializers.IntegerField(help_text="Quantas dicas o aluno pediu na sessão.")
    score_breakdowns = ScoreBreakdownSerializer(many=True)
    criteria = AttemptCriterionSerializer(many=True)


class TrackStateSerializer(serializers.Serializer):
    """Estado calculado de uma trilha, para a jornada do aluno."""

    slug = serializers.CharField(source="track.slug")
    title = serializers.CharField(source="track.title")
    order = serializers.IntegerField(source="track.order")
    student_role = serializers.CharField(
        source="track.student_role", help_text="O papel fixo do aluno em todos os cenários desta trilha."
    )
    unlocked = serializers.BooleanField(
        help_text="A primeira trilha está sempre liberada; as demais dependem da anterior concluída."
    )
    completed = serializers.BooleanField(help_text="Todos os cenários da trilha estão concluídos.")
    approved_levels = serializers.IntegerField(
        help_text="Quantas combinações de cenário e nível o aluno já aprovou nesta trilha."
    )
    possible_levels = serializers.IntegerField(
        help_text="Quantas combinações de cenário e nível existem no total nesta trilha."
    )
    performance = serializers.FloatField(
        allow_null=True,
        help_text="Média das notas dos cenários concluídos, ou nulo se nenhum foi concluído ainda.",
    )
    scenario_states = ScenarioStateSerializer(many=True)
