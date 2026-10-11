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

    def __init__(self, application, path: str, *args, **kwargs):
        url = urlsplit(path)
        query = parse_qs(url.query)
        self.token = query.pop("token", [None])[0]
        rest = urlencode({key: values[0] for key, values in query.items()})
        super().__init__(application, url.path + (f"?{rest}" if rest else ""), *args, **kwargs)

    async def connect(self, timeout: float = 1):
        connected, subprotocol = await super().connect(timeout)
        if connected and self.token is not None:
            await self.send_to(text_data=json.dumps({"type": "auth", "token": self.token}))
        return connected, subprotocol
