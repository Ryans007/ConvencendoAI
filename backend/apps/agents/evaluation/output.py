import contextlib
import io
from collections.abc import Iterator


@contextlib.contextmanager
def captured_output() -> Iterator[io.StringIO]:
    """Captura o que os nós do grafo imprimem, para a avaliação não despejar o log na tela.

    Devolve o buffer: quem chama pode procurar nele um aviso que o nó só imprime (como a falha
    do roteador, que o nó trata em silêncio).
    """
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        yield buffer
