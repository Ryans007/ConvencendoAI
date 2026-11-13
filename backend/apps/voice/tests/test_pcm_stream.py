import struct

import pytest

from apps.voice.services.pcm_stream import (
    EmptySpeechStream,
    PcmFormat,
    PcmStream,
    SpeechStreamError,
    UnsupportedSpeechFormat,
)


def wav_header(*, sample_rate: int = 24000, channels: int = 1, bits: int = 16, tag: int = 1) -> bytes:
    """O cabeçalho que o provedor manda: tamanhos 0xFFFFFFFF e um bloco LIST antes do áudio."""
    unknown = 0xFFFFFFFF
    fmt = struct.pack(
        "<HHIIHH", tag, channels, sample_rate, sample_rate * channels * bits // 8, channels * bits // 8, bits
    )
    info = b"INFOISFT" + struct.pack("<I", 14) + b"Lavf61.7.100\x00\x00"
    return (
        b"RIFF"
        + struct.pack("<I", unknown)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<I", len(fmt))
        + fmt
        + b"LIST"
        + struct.pack("<I", len(info))
        + info
        + b"data"
        + struct.pack("<I", unknown)
    )


def pcm(frames: int) -> bytes:
    return b"".join(struct.pack("<h", (index * 37) % 30000 - 15000) for index in range(frames))


def split(data: bytes, sizes: list[int]) -> list[bytes]:
    """Reparte `data` em pedaços de tamanhos dados, repetindo a lista até acabar."""
    chunks, position, turn = [], 0, 0
    while position < len(data):
        size = sizes[turn % len(sizes)]
        chunks.append(data[position : position + size])
        position += size
        turn += 1
    return chunks


def test_the_header_is_removed_wherever_the_provider_splits_it():
    source = pcm(500)
    stream_bytes = wav_header() + source
    header_length = len(wav_header())

    for cut in range(1, header_length + 3):
        chunks = [stream_bytes[:cut], stream_bytes[cut:]]

        assert b"".join(PcmStream(iter(chunks))) == source, f"cabeçalho partido em {cut}"


def test_every_chunk_ends_on_a_sample_boundary_even_when_the_provider_does_not():
    source = pcm(3000)
    raw = split(wav_header() + source, [701, 1203, 2001, 3001, 999])

    chunks = list(PcmStream(iter(raw)))

    assert all(len(chunk) % 2 == 0 for chunk in chunks)
    assert b"".join(chunks) == source


def test_a_dangling_byte_at_the_end_is_dropped_and_not_counted():
    source = pcm(100)
    stream = PcmStream(iter([wav_header() + source + b"\x07"]))

    assert b"".join(stream) == source
    assert stream.total_bytes == len(source)


def test_the_format_is_known_before_the_first_chunk_is_delivered():
    stream = PcmStream(iter([wav_header(sample_rate=24000) + pcm(50)]))

    next(iter(stream))

    assert stream.format == PcmFormat(sample_rate=24000, channels=1)


def test_the_total_counts_exactly_what_was_delivered():
    source = pcm(2500)
    stream = PcmStream(iter(split(wav_header() + source, [1001, 777])))

    delivered = b"".join(stream)

    assert stream.total_bytes == len(delivered) == len(source)


def test_a_format_that_is_not_16_bit_pcm_is_refused():
    stream = PcmStream(iter([wav_header(bits=8) + pcm(50)]))

    with pytest.raises(UnsupportedSpeechFormat):
        list(stream)


def test_a_compressed_format_is_refused():
    stream = PcmStream(iter([wav_header(tag=3) + pcm(50)]))

    with pytest.raises(UnsupportedSpeechFormat):
        list(stream)


def test_a_stream_with_only_a_header_is_an_empty_speech():
    with pytest.raises(EmptySpeechStream):
        list(PcmStream(iter([wav_header()])))


def test_a_stream_with_nothing_at_all_is_an_empty_speech():
    with pytest.raises(EmptySpeechStream):
        list(PcmStream(iter([])))


def test_audio_without_a_wav_header_is_refused():
    with pytest.raises(SpeechStreamError):
        list(PcmStream(iter([b"not a wav header at all" + pcm(50)])))


def test_a_header_that_never_reaches_the_audio_is_refused():
    endless = [b"RIFF" + b"\x00" * 4 + b"WAVE" + b"junk" + struct.pack("<I", 1 << 30)] + [b"\x00" * 1024] * 8

    with pytest.raises(SpeechStreamError):
        list(PcmStream(iter(endless)))
