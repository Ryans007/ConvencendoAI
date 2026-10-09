import re

_ENGLISH_MARKERS = frozenset(
    "the i we is are was were be been have has had need needs could would will which my "
    "our it its this that these those to of and for with by from at what can".split()
)
_PORTUGUESE_MARKERS = frozenset(
    "o a os as de do da dos das que e é em no na um uma para com não sim eu nós meu minha "
    "foi era porque mais isso esse essa por se já".split()
)
_WORD = re.compile(r"[a-zà-ú]+")


def looks_english(text: str) -> bool:
    """A sugestão parece escrita em inglês, e não em português?

    Conta palavras típicas de cada língua e decide pela que aparece mais. Nomes de
    tecnologias e de produtos não entram em nenhuma das duas listas, então uma sugestão em
    português cheia de nomes técnicos continua sendo português.
    """
    words = _WORD.findall(text.lower())
    english = sum(word in _ENGLISH_MARKERS for word in words)
    portuguese = sum(word in _PORTUGUESE_MARKERS for word in words)
    return english > portuguese
