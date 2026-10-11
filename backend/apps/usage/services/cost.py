from dataclasses import dataclass
from decimal import Decimal

_MILLION = Decimal(1_000_000)
_SECONDS_PER_HOUR = Decimal(3600)
_ZERO = Decimal(0)


@dataclass(frozen=True)
class Cost:
    """O custo estimado de uma chamada, em dólar, e se o modelo tinha preço cadastrado.

    Um modelo sem preço gera custo zero com `priced` falso, e não um erro: o uso é registrado
    do mesmo jeito, e o admin mostra que o custo dessa linha é desconhecido.
    """

    usd: Decimal
    priced: bool


def chat_cost(model, input_tokens: int, output_tokens: int) -> Cost:
    """Custo de uma chamada de chat: tokens de entrada e de saída, cada um com o seu preço.

    Só conta como precificado se os dois preços estão cadastrados; com um só, o custo seria
    subestimado sem aviso.
    """
    price_in = model.input_price_per_million_tokens
    price_out = model.output_price_per_million_tokens
    if price_in is None or price_out is None:
        return Cost(_ZERO, False)
    usd = (Decimal(input_tokens) * price_in + Decimal(output_tokens) * price_out) / _MILLION
    return Cost(usd, True)


def transcription_cost(model, audio_seconds: float | None) -> tuple[Cost, float | None]:
    """Custo de uma transcrição e os segundos cobrados, já com o mínimo do provedor.

    Sem a duração do áudio, o provedor não deu base de cálculo: custo zero e segundos
    cobrados vazios, sem falhar a transcrição.
    """
    price = model.price_per_audio_hour
    if audio_seconds is None:
        return Cost(_ZERO, price is not None), None
    billed = max(float(audio_seconds), float(model.min_billed_audio_seconds))
    if price is None:
        return Cost(_ZERO, False), billed
    return Cost(Decimal(str(billed)) * price / _SECONDS_PER_HOUR, True), billed


def speech_cost(model, characters: int) -> Cost:
    """Custo de uma síntese de voz, cobrada pelos caracteres do texto enviado."""
    price = model.price_per_million_characters
    if price is None:
        return Cost(_ZERO, False)
    return Cost(Decimal(characters) * price / _MILLION, True)
