import httpx
import langchain_openai.chat_models.base as langchain_base
import openai
import pytest

from apps.llm.services.factory import ModelNotConfigured
from apps.voice.services.failures import (
    FAILURE_DESCRIPTIONS,
    SessionErrorCode,
    classify_failure,
)

_REQUEST = httpx.Request("POST", "https://provider.example/v1/chat/completions")


def _status_error(error_class, status: int) -> openai.APIStatusError:
    response = httpx.Response(status, request=_REQUEST)
    return error_class("detalhe técnico do provedor", response=response, body=None)


def test_rate_limit_is_its_own_code():
    exc = _status_error(openai.RateLimitError, 429)

    assert classify_failure(exc) is SessionErrorCode.PROVIDER_RATE_LIMITED


@pytest.mark.parametrize(
    "exc",
    [
        openai.APIConnectionError(request=_REQUEST),
        openai.APITimeoutError(request=_REQUEST),
        _status_error(openai.InternalServerError, 503),
        _status_error(openai.AuthenticationError, 401),
        ModelNotConfigured("nenhum modelo ativo"),
    ],
)
def test_provider_that_is_down_or_unconfigured_is_unavailable(exc):
    assert classify_failure(exc) is SessionErrorCode.PROVIDER_UNAVAILABLE


def test_the_langchain_wrappers_that_the_provider_actually_raises_are_classified_too():
    rate_limited = langchain_base.OpenAIRateLimitError(
        "detalhe técnico do provedor", response=httpx.Response(429, request=_REQUEST), body=None
    )
    unreachable = langchain_base.OpenAIConnectionError(request=_REQUEST)
    timed_out = langchain_base.OpenAITimeoutError(request=_REQUEST)

    assert classify_failure(rate_limited) is SessionErrorCode.PROVIDER_RATE_LIMITED
    assert classify_failure(unreachable) is SessionErrorCode.PROVIDER_UNAVAILABLE
    assert classify_failure(timed_out) is SessionErrorCode.PROVIDER_UNAVAILABLE


@pytest.mark.parametrize("exc", [ValueError("bug"), KeyError("x"), RuntimeError("boom")])
def test_any_other_exception_is_unexpected(exc):
    assert classify_failure(exc) is SessionErrorCode.UNEXPECTED


def test_every_code_has_a_fixed_description_without_the_original_error():
    assert set(FAILURE_DESCRIPTIONS) == set(SessionErrorCode)
    for description in FAILURE_DESCRIPTIONS.values():
        assert description
        assert "detalhe técnico" not in description
