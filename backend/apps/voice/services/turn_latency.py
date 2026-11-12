import time
from dataclasses import dataclass

MAX_LATENCY_MS = 10 * 60 * 1000


@dataclass
class TurnMarks:
    """As medidas do servidor numa vez do aluno, preenchidas conforme as etapas terminam.

    `audio_received_at` é o relógio monotônico da chegada do áudio. As demais são durações em
    milissegundos, e ficam vazias até a etapa correspondente acabar.
    """

    audio_received_at: float
    stt_ms: int | None = None
    graph_ms: int | None = None
    tts_ms: int | None = None
    server_ms: int | None = None


def elapsed_ms(started_at: float) -> int:
    """Milissegundos inteiros desde um instante do relógio monotônico."""
    return int((time.monotonic() - started_at) * 1000)


def valid_latency_ms(raw: object) -> int | None:
    """A latência informada pelo navegador, ou vazia quando ela não serve como medida.

    O valor vem do cliente, então só vale um número entre 0 e 10 minutos: ausente, negativo,
    absurdo ou de outro tipo é descartado, e nada é registrado para a vez.
    """
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    if raw < 0 or raw > MAX_LATENCY_MS:
        return None
    return int(round(raw))


def format_turn_latency(attempt_id: int, turn: int, marks: TurnMarks, total_ms: int) -> str:
    """A linha de log de uma vez: o total sentido pelo aluno e as parcelas de cada etapa.

    `total_ms` vai do aluno soltar o botão até a primeira fala da persona começar a tocar.
    `outside_server_ms` é o que sobra depois de descontar o tempo do servidor: fechamento da
    gravação, envio do áudio, chegada da resposta e início da reprodução no navegador.
    """
    outside = total_ms - marks.server_ms if marks.server_ms is not None else None
    fields = {
        "attempt": attempt_id,
        "turn": turn,
        "total_ms": total_ms,
        "server_ms": marks.server_ms,
        "stt_ms": marks.stt_ms,
        "graph_ms": marks.graph_ms,
        "tts_ms": marks.tts_ms,
        "outside_server_ms": outside,
    }
    rendered = " ".join(f"{key}={'n/a' if value is None else value}" for key, value in fields.items())
    return f"[latency] {rendered}"
