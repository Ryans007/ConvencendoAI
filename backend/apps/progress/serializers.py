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
    expected_production = serializers.CharField(
        source="level.expected_production",
        help_text="O que se espera do aluno neste nível, em linguagem para o aluno.",
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


class CastMemberSerializer(serializers.Serializer):
    """Personagem do elenco de um cenário, como a jornada o exibe."""

    name = serializers.CharField(source="persona.name", help_text="Nome do personagem.")
    scene_function = serializers.CharField(
        help_text="Função do personagem na cena (ex.: 'recrutadora de RH')."
    )


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
    cast = CastMemberSerializer(
        many=True, help_text="Elenco do cenário, na ordem em que os personagens entram na cena."
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
    comment = serializers.CharField(
        help_text=(
            "Frase do avaliador, em português, que explica a nota. Vazia no objetivo e nas "
            "tentativas anteriores ao comentário."
        )
    )


class AttemptCriterionSerializer(serializers.Serializer):
    """Resultado de um critério avaliado numa tentativa."""

    code = serializers.CharField(help_text="Identificador curto do critério dentro do cenário.")
    text = serializers.CharField(
        source="text_at_time",
        help_text="Texto do critério como estava redigido no momento da tentativa.",
    )
    met = serializers.BooleanField(help_text="Se o aluno cumpriu este critério nesta tentativa.")


class AttemptMistakeSerializer(serializers.Serializer):
    """Um erro apontado na sessão, como o relatório o mostra: com a forma correta à vista."""

    id = serializers.IntegerField(help_text="Identificador do erro, que abre o áudio dele.")
    produced = serializers.CharField(help_text="A frase inteira que o aluno disse.")
    correct = serializers.CharField(help_text="A mesma frase corrigida.")
    explanation = serializers.CharField(
        help_text="A regra explicada em português; vazia nos erros anteriores à explicação."
    )
    examples = serializers.ListField(
        child=serializers.CharField(),
        help_text="Até duas frases em inglês que aplicam a mesma regra em outras situações.",
    )


class SpeechMetricsSerializer(serializers.Serializer):
    """As medidas de fala da sessão de voz que o nível da tentativa usa."""

    reaction_seconds = serializers.FloatField(
        allow_null=True, help_text="Mediana do tempo até começar a responder, em segundos."
    )
    words_per_minute = serializers.FloatField(
        allow_null=True, help_text="Velocidade da fala, em palavras por minuto."
    )
    long_pauses_per_100_words = serializers.FloatField(
        allow_null=True, help_text="Pausas de mais de 1,5 s no meio da fala, a cada 100 palavras."
    )
    lexical_diversity = serializers.FloatField(
        allow_null=True, help_text="Diversidade de palavras (MATTR), de 0 a 1."
    )
    lexical_range = serializers.FloatField(
        allow_null=True,
        help_text="Fração das palavras de conteúdo fora das 2.000 mais frequentes, de 0 a 1.",
    )


class FluencySharesSerializer(serializers.Serializer):
    """Quanto cada parte pesou na fluência medida."""

    measured_share = serializers.FloatField(help_text="Fatia da medida na nota; o resto é da IA.")
    reaction_share = serializers.FloatField()
    speed_share = serializers.FloatField()
    pauses_share = serializers.FloatField()


class VocabularySharesSerializer(serializers.Serializer):
    """Quanto cada parte pesou no vocabulário medido."""

    judged_share = serializers.FloatField(help_text="Fatia do julgamento da IA (precisão).")
    diversity_share = serializers.FloatField()
    range_share = serializers.FloatField()


class ReportScoringSerializer(serializers.Serializer):
    """O que a tela precisa para explicar como a nota foi calculada."""

    passing_score = serializers.IntegerField(help_text="Nota mínima de aprovação.")
    fluency = FluencySharesSerializer(
        allow_null=True, help_text="Proporções da fluência, ou nulo quando ela não foi medida."
    )
    vocabulary = VocabularySharesSerializer(
        allow_null=True, help_text="Proporções do vocabulário, ou nulo quando ele não foi medido."
    )


class AttemptReportSerializer(serializers.Serializer):
    """Relatório completo de uma tentativa já concluída: nota final, sub-nota e comentário por
    dimensão, resultado de cada critério aplicável, resumo do avaliador, erros da sessão,
    medidas de fala e a explicação da conta da nota.
    """

    id = serializers.IntegerField(source="attempt.id")
    scenario = serializers.CharField(source="attempt.scenario.slug")
    level = serializers.IntegerField(source="attempt.level.order")
    final_score = serializers.IntegerField(
        source="attempt.final_score",
        help_text="Nota de 0 a 100, normalizada sobre o peso avaliado.",
    )
    passed = serializers.BooleanField(
        source="attempt.passed", help_text="Se a nota atingiu o mínimo de aprovação."
    )
    feedback = serializers.CharField(
        source="attempt.feedback",
        help_text="Resumo do avaliador, em português nas tentativas novas.",
    )
    completed_at = serializers.DateTimeField(source="attempt.completed_at")
    hints_enabled = serializers.BooleanField(
        source="attempt.hints_enabled", help_text="O aluno começou a sessão com as dicas ligadas."
    )
    hints_used = serializers.IntegerField(
        source="attempt.hints_used", help_text="Quantas dicas o aluno pediu na sessão."
    )
    score_breakdowns = ScoreBreakdownSerializer(source="attempt.score_breakdowns", many=True)
    criteria = AttemptCriterionSerializer(source="attempt.criteria", many=True)
    mistakes = AttemptMistakeSerializer(
        many=True, help_text="Erros apontados na sessão, sem os que o aluno arquivou; até 4."
    )
    speech_metrics = SpeechMetricsSerializer(
        allow_null=True, help_text="Medidas de fala da sessão de voz, ou nulo sem medidas."
    )
    scoring = ReportScoringSerializer()


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
