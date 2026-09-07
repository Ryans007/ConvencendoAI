from apps.llm.constants import ModelCategory
from apps.llm.services.factory import get_audio_client


def synthesize(text: str, voice: str) -> bytes:
    """Sintetiza a fala de uma persona em áudio, via o modelo de TTS configurado.

    Devolve o WAV pronto exatamente como o provedor entrega — sem decodificar nem
    recodificar, já que ninguém aqui precisa manipular a amostra, só encaminhá-la.
    """
    resolved = get_audio_client(ModelCategory.TTS)
    response = resolved.client.audio.speech.create(
        model=resolved.model_id,
        voice=voice,
        input=text,
        response_format="wav",
    )
    return response.read()
