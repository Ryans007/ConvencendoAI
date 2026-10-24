import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from functools import cache
from statistics import median
from typing import Protocol

from wordfreq import top_n_list

from apps.progress.models import SpeechTurn
from apps.progress.speech_bands import (
    COMMON_WORDS_COUNT,
    LONG_PAUSE_SECONDS,
    MATTR_WINDOW,
    MIN_WORDS_FOR_VOCABULARY,
)

_TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*")

_FUNCTION_WORDS = frozenset(
    """
    a an the and or but so if because than then as of at by for from in into on onto to with
    without about after before over under up down out off through between i me my mine you your
    yours he him his she her hers it its we us our ours they them their theirs this that these
    those who whom whose which what where when why how is am are was were be been being have has
    had having do does did doing will would shall should can could may might must not no yes
    there here very just also too please uh um oh ok okay
    """.split()
)


class TimedWord(Protocol):
    """Uma palavra com o início e o fim, em segundos desde o começo da gravação."""

    start: float
    end: float


@dataclass(frozen=True)
class TurnMeasure:
    """As medidas de uma vez de fala, tiradas dos horários das palavras."""

    leading_silence_ms: int
    speech_ms: int
    word_count: int
    long_pauses: int


@dataclass(frozen=True)
class SessionSpeechMetrics:
    """As medidas de fala de uma sessão inteira.

    Cada medida fica vazia quando a sessão não tem o necessário para ela: a reação, sem nenhuma
    vez com espera conhecida fora de dica; a velocidade e as pausas, sem tempo de fala; a
    diversidade e o alcance, com menos palavras do que o mínimo para a medida fazer sentido.
    """

    reaction_seconds: float | None
    words_per_minute: float | None
    long_pauses_per_100_words: float | None
    lexical_diversity: float | None
    lexical_range: float | None
    word_count: int


def measure_turn(words: Sequence[TimedWord]) -> TurnMeasure | None:
    """As medidas de uma vez a partir das palavras com horário; sem palavras, não há medida.

    Uma pausa longa é um intervalo maior que 1,5 segundo entre o fim de uma palavra e o começo
    da seguinte.
    """
    if not words:
        return None
    first, last = words[0], words[-1]
    long_pauses = sum(
        1
        for previous, current in zip(words, words[1:])
        if current.start - previous.end > LONG_PAUSE_SECONDS
    )
    return TurnMeasure(
        leading_silence_ms=int(round(max(0.0, first.start) * 1000)),
        speech_ms=int(round(max(0.0, last.end - first.start) * 1000)),
        word_count=len(words),
        long_pauses=long_pauses,
    )


def session_metrics(
    turns: Sequence[SpeechTurn], excluded_names: Collection[str] = ()
) -> SessionSpeechMetrics | None:
    """As medidas da sessão a partir das vezes gravadas; sem vezes, a sessão não tem medidas.

    A reação é a mediana, para que uma vez em que o aluno se distraiu não decida a medida, e
    deixa de fora as vezes depois de dica, que já pesam na autonomia. A velocidade e as pausas
    somam todas as vezes, para uma vez curta não pesar tanto quanto uma longa. `excluded_names`
    são os nomes das personas, que não contam como vocabulário do aluno.
    """
    if not turns:
        return None

    reactions = [
        (turn.waited_ms + turn.leading_silence_ms) / 1000
        for turn in turns
        if turn.waited_ms is not None and not turn.after_hint
    ]
    total_words = sum(turn.word_count for turn in turns)
    total_speech_minutes = sum(turn.speech_ms for turn in turns) / 60000
    tokens = _student_tokens([turn.text for turn in turns], excluded_names)
    enough_words = len(tokens) >= MIN_WORDS_FOR_VOCABULARY

    return SessionSpeechMetrics(
        reaction_seconds=median(reactions) if reactions else None,
        words_per_minute=(
            total_words / total_speech_minutes if total_speech_minutes > 0 else None
        ),
        long_pauses_per_100_words=(
            sum(turn.long_pauses for turn in turns) / total_words * 100 if total_words else None
        ),
        lexical_diversity=moving_average_type_token_ratio(tokens) if enough_words else None,
        lexical_range=lexical_range(tokens) if enough_words else None,
        word_count=len(tokens),
    )


def moving_average_type_token_ratio(tokens: Sequence[str], window: int = MATTR_WINDOW) -> float:
    """A diversidade de palavras por MATTR: a média da proporção de palavras diferentes em cada
    janela de `window` palavras seguidas.

    A proporção simples (diferentes ÷ total) cai à medida que o texto cresce, o que puniria quem
    fala mais; a média em janelas de tamanho fixo não depende do tamanho da fala.
    """
    if not tokens:
        return 0.0
    if len(tokens) <= window:
        return len(set(tokens)) / len(tokens)
    ratios = [
        len(set(tokens[start : start + window])) / window
        for start in range(len(tokens) - window + 1)
    ]
    return sum(ratios) / len(ratios)


def lexical_range(tokens: Sequence[str]) -> float:
    """A fração das palavras de conteúdo do aluno que está fora das 2.000 mais frequentes do
    inglês. Palavras funcionais (artigos, preposições, pronomes, auxiliares) ficam fora da conta.
    """
    content = [token for token in tokens if token not in _FUNCTION_WORDS]
    if not content:
        return 0.0
    common = _common_words()
    return sum(1 for token in content if token not in common) / len(content)


@cache
def _common_words() -> frozenset[str]:
    """As palavras mais frequentes do inglês, carregadas uma vez por processo."""
    return frozenset(top_n_list("en", COMMON_WORDS_COUNT))


def _student_tokens(texts: Sequence[str], excluded_names: Collection[str]) -> list[str]:
    """As palavras do aluno em minúsculas, sem os nomes próprios.

    Um nome não é vocabulário: "Emma" ou "Lisbon" contariam como palavras raras e inflariam o
    alcance. Saem os nomes das personas e as palavras com inicial maiúscula fora do começo de
    uma frase, que é como o STT escreve um nome próprio. O "I" e as contrações dele ("I'm") ficam,
    porque são sempre maiúsculos.
    """
    names = {name.lower() for name in excluded_names}
    tokens: list[str] = []
    for text in texts:
        for match in _TOKEN.finditer(text):
            word = match.group(0)
            lowered = word.lower()
            if lowered in names:
                continue
            before = text[: match.start()].rstrip()
            starts_sentence = not before or before[-1] in ".!?"
            is_pronoun_i = lowered == "i" or lowered.startswith("i'")
            if word[0].isupper() and not is_pronoun_i and not starts_sentence:
                continue
            tokens.append(lowered)
    return tokens
