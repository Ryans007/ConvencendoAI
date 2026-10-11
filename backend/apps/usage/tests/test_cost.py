from decimal import Decimal
from types import SimpleNamespace

from apps.usage.services.cost import chat_cost, speech_cost, transcription_cost


def _model(**prices) -> SimpleNamespace:
    defaults = {
        "input_price_per_million_tokens": None,
        "output_price_per_million_tokens": None,
        "price_per_audio_hour": None,
        "min_billed_audio_seconds": 0,
        "price_per_million_characters": None,
    }
    return SimpleNamespace(**{**defaults, **prices})


def test_the_chat_cost_uses_the_input_and_output_prices():
    model = _model(
        input_price_per_million_tokens=Decimal("0.10"),
        output_price_per_million_tokens=Decimal("0.50"),
    )

    cost = chat_cost(model, input_tokens=1000, output_tokens=200)

    assert cost.usd == Decimal("0.0002")
    assert cost.priced is True


def test_a_chat_model_with_only_one_price_is_not_taken_as_priced():
    model = _model(input_price_per_million_tokens=Decimal("0.10"))

    cost = chat_cost(model, input_tokens=1000, output_tokens=200)

    assert cost.usd == 0
    assert cost.priced is False


def test_a_chat_model_without_prices_costs_zero_and_is_not_priced():
    cost = chat_cost(_model(), input_tokens=5000, output_tokens=500)

    assert cost.usd == 0
    assert cost.priced is False


def test_the_transcription_is_billed_at_least_the_minimum_seconds():
    model = _model(price_per_audio_hour=Decimal("0.04"), min_billed_audio_seconds=10)

    cost, billed = transcription_cost(model, 2.0)

    assert billed == 10
    assert cost.usd == Decimal("10") * Decimal("0.04") / Decimal(3600)
    assert cost.priced is True


def test_a_transcription_longer_than_the_minimum_is_billed_as_it_is():
    model = _model(price_per_audio_hour=Decimal("0.04"), min_billed_audio_seconds=10)

    _, billed = transcription_cost(model, 25.5)

    assert billed == 25.5


def test_a_transcription_without_duration_costs_zero_without_failing():
    model = _model(price_per_audio_hour=Decimal("0.04"), min_billed_audio_seconds=10)

    cost, billed = transcription_cost(model, None)

    assert cost.usd == 0
    assert billed is None


def test_a_transcription_model_without_price_costs_zero_and_is_not_priced():
    cost, billed = transcription_cost(_model(), 3.0)

    assert cost.usd == 0
    assert cost.priced is False
    assert billed == 3.0


def test_the_speech_cost_uses_the_characters():
    model = _model(price_per_million_characters=Decimal("22.00"))

    cost = speech_cost(model, characters=40)

    assert cost.usd == Decimal("0.00088")
    assert cost.priced is True


def test_a_speech_model_without_price_costs_zero_and_is_not_priced():
    cost = speech_cost(_model(), characters=40)

    assert cost.usd == 0
    assert cost.priced is False
