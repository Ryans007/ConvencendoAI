from dataclasses import dataclass


@dataclass(frozen=True)
class Band:
    """Uma faixa que transforma uma medida numa fração de 0 a 1.

    Vale 1 no limite `full` ou além dele, 0 no limite `zero` ou além dele, e cai em linha reta
    entre os dois. Serve tanto para medidas em que menos é melhor (reação, pausas) quanto para as
    em que mais é melhor (velocidade, diversidade): o sentido vem da ordem dos dois limites.
    """

    full: float
    zero: float

    def fraction(self, value: float) -> float:
        """A fração de 0 a 1 que a medida vale nesta faixa."""
        if self.full == self.zero:
            return 1.0 if value == self.full else 0.0
        position = (value - self.zero) / (self.full - self.zero)
        return max(0.0, min(1.0, position))


@dataclass(frozen=True)
class FluencyRules:
    """As faixas de fluência de um nível e quanto cada medida pesa na fluência medida.

    Um nível sem faixa de velocidade ou de pausas mede só a reação: no nível 1 as respostas são
    "yes" e "no", e velocidade ou pausas numa palavra solta não dizem nada.
    """

    reaction: Band
    speed: Band | None
    pauses: Band | None
    reaction_share: float
    speed_share: float
    pauses_share: float


@dataclass(frozen=True)
class VocabularyRules:
    """Quanto o julgamento da IA, a diversidade e o alcance pesam no vocabulário de um nível.

    Diversidade e alcance só contam quando o nível pede respostas desenvolvidas: nos níveis
    baixos, palavras básicas são exatamente o esperado.
    """

    judged_share: float
    diversity_share: float
    range_share: float


@dataclass(frozen=True)
class LevelSpeechRules:
    """As regras de medida de fala de um nível."""

    fluency: FluencyRules
    vocabulary: VocabularyRules


MEASURED_FLUENCY_SHARE = 0.7
LONG_PAUSE_SECONDS = 1.5
MAX_WAIT_MS = 10 * 60 * 1000
MIN_WORDS_FOR_VOCABULARY = 50
MATTR_WINDOW = 25
COMMON_WORDS_COUNT = 2000
DIVERSITY_BAND = Band(full=0.70, zero=0.45)
RANGE_BAND = Band(full=0.10, zero=0.0)

_RULES_BY_LEVEL_ORDER = {
    1: LevelSpeechRules(
        fluency=FluencyRules(
            reaction=Band(full=4.0, zero=12.0),
            speed=None,
            pauses=None,
            reaction_share=1.0,
            speed_share=0.0,
            pauses_share=0.0,
        ),
        vocabulary=VocabularyRules(judged_share=1.0, diversity_share=0.0, range_share=0.0),
    ),
    2: LevelSpeechRules(
        fluency=FluencyRules(
            reaction=Band(full=3.0, zero=10.0),
            speed=Band(full=80.0, zero=40.0),
            pauses=Band(full=3.0, zero=12.0),
            reaction_share=0.4,
            speed_share=0.4,
            pauses_share=0.2,
        ),
        vocabulary=VocabularyRules(judged_share=0.7, diversity_share=0.3, range_share=0.0),
    ),
    3: LevelSpeechRules(
        fluency=FluencyRules(
            reaction=Band(full=2.5, zero=8.0),
            speed=Band(full=100.0, zero=40.0),
            pauses=Band(full=2.0, zero=10.0),
            reaction_share=0.4,
            speed_share=0.4,
            pauses_share=0.2,
        ),
        vocabulary=VocabularyRules(judged_share=0.5, diversity_share=0.25, range_share=0.25),
    ),
}


def rules_for_level(level_order: int) -> LevelSpeechRules:
    """As regras do nível pela ordem dele.

    Um nível novo, sem entrada própria, usa as regras do nível mais alto abaixo dele; um nível
    abaixo de todos usa as do primeiro. Assim cadastrar um nível no admin nunca quebra a
    avaliação, e a calibração mexe só nesta tabela.
    """
    known = sorted(_RULES_BY_LEVEL_ORDER)
    below = [order for order in known if order <= level_order]
    return _RULES_BY_LEVEL_ORDER[below[-1] if below else known[0]]
