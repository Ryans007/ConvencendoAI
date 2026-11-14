import json
from urllib.parse import parse_qs, urlencode, urlsplit

from channels.testing import WebsocketCommunicator


class SessionCommunicator(WebsocketCommunicator):
    """Abre a sessão de voz como o frontend: sem token na URL e autenticando na primeira mensagem.

    Os testes escrevem o caminho com `?token=...` por conveniência. O auxiliar tira o token da
    URL, que nunca o leva de verdade, abre a conexão e manda a mensagem de autenticação logo
    que ela abre. Sem token no caminho, nada é enviado, e quem testa o protocolo manda o que
    quiser. Os parâmetros que sobram, como `hints`, seguem na URL.
    """

    def __init__(self, application, path: str, *args, stream_audio: bool = False, **kwargs):
        self.stream_audio = stream_audio
        url = urlsplit(path)
        query = parse_qs(url.query)
        self.token = query.pop("token", [None])[0]
        rest = urlencode({key: values[0] for key, values in query.items()})
        super().__init__(application, url.path + (f"?{rest}" if rest else ""), *args, **kwargs)

    async def connect(self, timeout: float = 1):
        connected, subprotocol = await super().connect(timeout)
        if connected and self.token is not None:
            auth = {"type": "auth", "token": self.token}
            if self.stream_audio:
                auth["stream_audio"] = True
            await self.send_to(text_data=json.dumps(auth))
        return connected, subprotocol

    async def receive_persona_line(self) -> tuple[str, bytes]:
        """Lê uma fala de persona como o cliente a recebe: o nome de quem fala, depois o áudio.

        Falha se o nome não vier antes do áudio.
        """
        announced = json.loads(await self.receive_from())
        assert announced["type"] == "speaker"
        return announced["name"], await self.receive_from()

    async def receive_persona_audio(self, audio: bytes = b"fake-wav-bytes") -> str:
        """Lê uma fala de persona, confere o áudio e devolve o nome de quem falou."""
        name, received = await self.receive_persona_line()
        assert received == audio
        return name
