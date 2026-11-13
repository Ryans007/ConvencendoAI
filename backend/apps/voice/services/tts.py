import time
from collections.abc import Iterator

from apps.llm.constants import ModelCategory
from apps.llm.services.factory import get_audio_client
from apps.usage.services.recording import record_speech_call
from apps.voice.services.pcm_stream import EmptySpeechStream, PcmFormat, PcmStream


def synthesize(text: str, voice: str) -> bytes:
    """Sintetiza a fala de uma persona em áudio, via o modelo de TTS configurado.

    Devolve o WAV pronto exatamente como o provedor entrega — sem decodificar nem
    recodificar, já que ninguém aqui precisa manipular a amostra, só encaminhá-la. O provedor
    não informa o uso, mas cobra pelos caracteres do texto, que são os que enviamos: é isso que
    a chamada, com ou sem falha, grava como uso do modelo.
    """
    resolved = get_audio_client(ModelCategory.TTS)
    started_at = time.monotonic()
    try:
        response = resolved.client.audio.speech.create(
            model=resolved.model_id,
            voice=voice,
            input=text,
            response_format="wav",
        )
        audio = response.read()
    except Exception as exc:
        _record(resolved, len(text), started_at, failed=True, error_code=type(exc).__name__)
        raise
    _record(resolved, len(text), started_at)
    return audio


def _record(resolved, characters: int, started_at: float, **failure) -> None:
    if resolved.model is None:
        return
    record_speech_call(
        llm_model=resolved.model,
        characters=characters,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        **failure,
    )


class SpeechStream:
    """A fala de uma persona sendo sintetizada em fluxo, como PCM cru e em pedaços alinhados.

    Faz com `synthesize` o que `PcmStream` não sabe: pedir a síntese ao provedor e gravar o uso.
    O uso é gravado uma única vez, ao fim da iteração, e cobra os caracteres do texto nos dois
    desfechos em que o provedor já cobrou: a fala que terminou e a fala que quem consome
    abandonou no meio, como numa conexão que cai. Só a falha, inclusive a de uma síntese sem
    áudio, é gravada como falha e sem custo. `format` e `total_bytes` são os do `PcmStream`.
    """

    def __init__(self, text: str, voice: str):
        self._resolved = get_audio_client(ModelCategory.TTS)
        self._text = text
        self._voice = voice
        self._started_at = time.monotonic()
        self._recorded = False
        self._pcm = PcmStream(self._provider_chunks())

    @property
    def format(self) -> PcmFormat | None:
        return self._pcm.format

    @property
    def total_bytes(self) -> int:
        return self._pcm.total_bytes

    def __iter__(self) -> Iterator[bytes]:
        try:
            yield from self._pcm
        except GeneratorExit:
            self._record_once()
            raise
        except Exception as exc:
            self._record_once(failed=True, error_code=type(exc).__name__)
            raise
        self._record_once()

    def _provider_chunks(self) -> Iterator[bytes]:
        with self._resolved.client.audio.speech.with_streaming_response.create(
            model=self._resolved.model_id,
            voice=self._voice,
            input=self._text,
            response_format="wav",
        ) as response:
            yield from response.iter_bytes()

    def _record_once(self, **failure) -> None:
        if self._recorded:
            return
        self._recorded = True
        _record(self._resolved, len(self._text), self._started_at, **failure)


def synthesize_stream(text: str, voice: str) -> SpeechStream:
    """Sintetiza a fala de uma persona em fluxo: PCM cru que chega à medida que é gerado.

    Devolve um iterável de pedaços de áudio que só termina quando o provedor termina. Quem
    consome precisa ler o primeiro pedaço antes de usar `format`, e confere o fim da fala pelo
    `total_bytes`. A falha do provedor, no começo ou no meio, é levantada na iteração.
    """
    return SpeechStream(text, voice)
