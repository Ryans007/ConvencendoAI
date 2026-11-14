import struct
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

MAX_HEADER_BYTES = 4096
PCM_FORMAT_TAG = 1
SAMPLE_BITS = 16
BYTES_PER_SAMPLE = SAMPLE_BITS // 8


class SpeechStreamError(ValueError):
    """O áudio que o provedor mandou não tem a forma que o fluxo de fala espera."""


class UnsupportedSpeechFormat(SpeechStreamError):
    """O áudio não é PCM de 16 bits, o único formato que o navegador sabe agendar."""


class EmptySpeechStream(SpeechStreamError):
    """O provedor terminou a síntese sem mandar nenhum áudio."""


@dataclass(frozen=True)
class PcmFormat:
    """A taxa de amostragem e o número de canais do áudio de uma fala."""

    sample_rate: int
    channels: int


def _parse_header(buffer: bytes) -> tuple[PcmFormat, int] | None:
    """Lê o cabeçalho WAV acumulado e devolve o formato e onde o áudio começa.

    Devolve `None` enquanto o cabeçalho ainda está incompleto, porque o provedor o entrega
    partido entre os primeiros pedaços. Os blocos são percorridos um a um até o `data`, e não
    procurados por texto, porque o bloco `LIST` que vem antes carrega texto livre. O tamanho do
    próprio `data` é ignorado: o provedor o declara como 0xFFFFFFFF, de fluxo sem fim conhecido.
    """
    if len(buffer) < 12:
        return None
    if not (buffer.startswith(b"RIFF") and buffer[8:12] == b"WAVE"):
        raise SpeechStreamError("áudio sem cabeçalho WAV")
    offset = 12
    fmt: PcmFormat | None = None
    while True:
        if len(buffer) < offset + 8:
            return None
        chunk_id = buffer[offset : offset + 4]
        size = struct.unpack_from("<I", buffer, offset + 4)[0]
        if chunk_id == b"data":
            if fmt is None:
                raise SpeechStreamError("cabeçalho WAV sem o bloco de formato")
            return fmt, offset + 8
        if chunk_id == b"fmt ":
            if len(buffer) < offset + 8 + 16:
                return None
            tag, channels, rate, _, _, bits = struct.unpack_from("<HHIIHH", buffer, offset + 8)
            if tag != PCM_FORMAT_TAG or bits != SAMPLE_BITS:
                raise UnsupportedSpeechFormat(f"formato WAV {tag} de {bits} bits não suportado")
            fmt = PcmFormat(sample_rate=rate, channels=channels)
        offset += 8 + size + (size & 1)


class PcmStream:
    """O áudio de uma fala como PCM cru, sem cabeçalho e sempre em pedaços de amostras inteiras.

    Consome os pedaços que o provedor manda, tira o cabeçalho WAV e só entrega múltiplos do
    tamanho de uma amostra, guardando o que sobra para o pedaço seguinte: uma amostra partida
    entre dois pedaços viraria estalo no navegador. `format` fica conhecido antes do primeiro
    pedaço entregue, e `total_bytes` conta só o que foi entregue, que é o que o marcador de fim
    da fala informa. Um byte solto no fim, que não completa uma amostra, é descartado. O fluxo de
    origem é sempre fechado ao fim da iteração, inclusive quando quem consome desiste no meio.
    """

    def __init__(self, raw_chunks: Iterable[bytes]):
        self._raw = iter(raw_chunks)
        self.format: PcmFormat | None = None
        self.total_bytes = 0

    def __iter__(self) -> Iterator[bytes]:
        try:
            yield from self._pcm_chunks()
        finally:
            close = getattr(self._raw, "close", None)
            if close is not None:
                close()

    def _pcm_chunks(self) -> Iterator[bytes]:
        header = b""
        header_done = False
        carry = b""
        received_anything = False
        frame_bytes = BYTES_PER_SAMPLE
        for raw in self._raw:
            if not raw:
                continue
            received_anything = True
            if not header_done:
                header += raw
                parsed = _parse_header(header)
                if parsed is None:
                    if len(header) > MAX_HEADER_BYTES:
                        raise SpeechStreamError("cabeçalho WAV longo demais")
                    continue
                self.format, start = parsed
                frame_bytes = self.format.channels * BYTES_PER_SAMPLE
                header_done = True
                raw, header = header[start:], b""
                if not raw:
                    continue
            data = carry + raw
            usable = len(data) - len(data) % frame_bytes
            carry = data[usable:]
            if usable:
                self.total_bytes += usable
                yield data[:usable]
        if not received_anything:
            raise EmptySpeechStream("a síntese não mandou áudio")
        if not header_done:
            raise SpeechStreamError("áudio sem cabeçalho WAV")
        if self.total_bytes == 0:
            raise EmptySpeechStream("a síntese não mandou áudio")
