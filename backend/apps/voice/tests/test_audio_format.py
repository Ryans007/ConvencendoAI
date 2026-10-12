import pytest

from apps.voice.services.audio_format import detect_audio_format

WEBM = b"\x1a\x45\xdf\xa3" + b"\x9fB\x86\x81\x01"
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
OGG = b"OggS\x00\x02" + b"\x00" * 20
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt "


@pytest.mark.parametrize(
    ("audio", "expected"),
    [(WEBM, "webm"), (MP4, "mp4"), (OGG, "ogg"), (WAV, "wav")],
)
def test_each_browser_format_is_recognised_by_its_content(audio, expected):
    assert detect_audio_format(audio) == expected


@pytest.mark.parametrize("audio", [b"", b"abc", b"raw-student-audio", b"RIFF\x00\x00\x00\x00AVI "])
def test_an_unknown_content_is_not_guessed(audio):
    assert detect_audio_format(audio) is None
