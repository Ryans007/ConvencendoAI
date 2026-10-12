import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LiveSession, type LiveSessionState } from "./liveSession";

vi.mock("./session", () => ({
  getAccessToken: () => "fake-token",
}));

class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  readyState = FakeWebSocket.CONNECTING;
  binaryType = "blob";
  readonly url: string;
  readonly sent: unknown[] = [];
  private readonly listeners: Record<string, Array<(event: unknown) => void>> = {};

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  addEventListener(type: string, listener: (event: unknown) => void): void {
    (this.listeners[type] ??= []).push(listener);
  }

  send(data: unknown): void {
    this.sent.push(data);
  }

  close(): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.dispatch("close", {});
  }

  dispatch(type: string, event: unknown): void {
    if (type === "open") {
      this.readyState = FakeWebSocket.OPEN;
    }
    for (const listener of this.listeners[type] ?? []) {
      listener(event);
    }
  }
}

class FakeAudio {
  static instances: FakeAudio[] = [];
  static nextPlayRejects = false;
  src = "";
  error: Error | null = null;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  readonly played: string[] = [];

  constructor() {
    FakeAudio.instances.push(this);
  }

  play(): Promise<void> {
    this.played.push(this.src);
    if (FakeAudio.nextPlayRejects) {
      FakeAudio.nextPlayRejects = false;
      return Promise.reject(new DOMException("recusado", "NotAllowedError"));
    }
    return Promise.resolve();
  }

  triggerEnded(): void {
    this.onended?.();
  }
}

/** Termina o áudio que está tocando e deixa a sessão seguir para o próximo da fila. */
async function endAudio(): Promise<void> {
  FakeAudio.instances[0].triggerEnded();
  await Promise.resolve();
}

/** O player da sessão: um só elemento de áudio por sessão. */
function player(): FakeAudio {
  return FakeAudio.instances[0];
}

/** As falas das personas que o player já começou a tocar, sem contar o silêncio de liberação. */
function spokenLines(): string[] {
  return player().played.filter((src) => !src.startsWith("blob:silence"));
}

function collectStates(session: LiveSession): LiveSessionState[] {
  const states: LiveSessionState[] = [];
  session.subscribe((state) => states.push(state));
  return states;
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  FakeAudio.instances = [];
  FakeAudio.nextPlayRejects = false;
  vi.stubGlobal("WebSocket", FakeWebSocket);
  vi.stubGlobal("Audio", FakeAudio);
  vi.stubGlobal("location", { protocol: "https:", host: "app.exemplo.com.br" });
  let blobCount = 0;
  vi.stubGlobal(
    "URL",
    Object.assign(URL, {
      createObjectURL: (blob: Blob) =>
        blob.size === 1644 ? "blob:silence" : `blob:fake-${(blobCount += 1)}`,
      revokeObjectURL: () => undefined,
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("services/liveSession", () => {
  it("abre a conexao no mesmo host da pagina quando o build nao configura a URL", () => {
    vi.stubEnv("VITE_WS_BASE_URL", "");

    new LiveSession("negociar-prazo", 3);

    expect(FakeWebSocket.instances[0].url).toBe(
      "wss://app.exemplo.com.br/ws/voice/negociar-prazo/3/",
    );
  });

  it("toca o audio das personas em sequencia, nunca dois ao mesmo tempo", async () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    socket.dispatch("open", {});

    socket.dispatch("message", { data: new ArrayBuffer(4) });
    socket.dispatch("message", { data: new ArrayBuffer(4) });

    expect(FakeAudio.instances).toHaveLength(1);
    expect(spokenLines()).toHaveLength(1);

    await endAudio();
    expect(FakeAudio.instances).toHaveLength(1);
    expect(spokenLines()).toHaveLength(2);

    const states = collectStates(session);
    await endAudio();

    expect(states.at(-1)?.phase).toBe("student-turn");
    expect(states.at(-1)?.turnCount).toBe(1);
  });

  it("nao avanca em silencio quando o navegador recusa tocar o audio", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    FakeAudio.nextPlayRejects = true;

    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    const states = collectStates(session);
    socket.dispatch("open", {});

    socket.dispatch("message", { data: new ArrayBuffer(4) });
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(errorSpy).toHaveBeenCalledWith(
      "Falha ao reproduzir audio da persona:",
      expect.any(Error),
    );
    expect(states.at(-1)?.phase).toBe("student-turn");
    expect(socket.sent).toContain(
      JSON.stringify({ type: "playback_failed", reason: "NotAllowedError" }),
    );

    errorSpy.mockRestore();
  });

  it("so resolve o fim de sessao depois que o ultimo audio termina de tocar", async () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    const states = collectStates(session);
    socket.dispatch("open", {});

    socket.dispatch("message", { data: new ArrayBuffer(4) });
    socket.dispatch("message", {
      data: JSON.stringify({ type: "session_ended", attempt_id: 42, final_score: 90, passed: true }),
    });

    expect(states.at(-1)?.phase).toBe("persona-speaking");

    await endAudio();

    expect(states.at(-1)?.phase).toBe("ended");
    expect(states.at(-1)?.result).toEqual({ attemptId: 42, finalScore: 90, passed: true });
  });

  it("fala longa demais, devolve a vez ao aluno com aviso e sem encerrar a sessão", async () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    const states = collectStates(session);
    socket.dispatch("open", {});
    socket.dispatch("message", { data: new ArrayBuffer(4) });
    await endAudio();

    socket.dispatch("message", { data: JSON.stringify({ type: "audio_too_large" }) });

    expect(states.at(-1)?.phase).toBe("student-turn");
    expect(states.at(-1)?.audioTooLargeNotice).toBe(true);
    expect(states.at(-1)?.noSpeechNotice).toBe(false);
    expect(states.at(-1)?.turnCount).toBe(1);
  });

  it("sem fala detectada, devolve a vez ao aluno com aviso e sem contar turno", async () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    const states = collectStates(session);
    socket.dispatch("open", {});

    socket.dispatch("message", { data: new ArrayBuffer(4) });
    await endAudio();
    expect(states.at(-1)?.turnCount).toBe(1);

    socket.dispatch("message", { data: JSON.stringify({ type: "no_speech" }) });

    expect(states.at(-1)?.phase).toBe("student-turn");
    expect(states.at(-1)?.noSpeechNotice).toBe(true);
    expect(states.at(-1)?.turnCount).toBe(1);
  });

  it("depois do aviso de avaliacao, o fim do audio leva a fase de avaliacao, e nao a vez do aluno", async () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    const states = collectStates(session);
    socket.dispatch("open", {});

    socket.dispatch("message", { data: new ArrayBuffer(4) });
    socket.dispatch("message", { data: JSON.stringify({ type: "evaluating" }) });
    await endAudio();

    expect(states.at(-1)?.phase).toBe("evaluating");
    expect(states.some((state) => state.phase === "student-turn")).toBe(false);

    socket.dispatch("message", {
      data: JSON.stringify({ type: "session_ended", attempt_id: 7, final_score: 80, passed: true }),
    });

    expect(states.at(-1)?.phase).toBe("ended");
    expect(states.at(-1)?.result).toEqual({ attemptId: 7, finalScore: 80, passed: true });
  });

  it("o fechamento logo apos o fim de sessao nao vira conexao perdida enquanto o audio toca", async () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    const states = collectStates(session);
    socket.dispatch("open", {});

    socket.dispatch("message", { data: new ArrayBuffer(4) });
    socket.dispatch("message", {
      data: JSON.stringify({ type: "session_ended", attempt_id: 7, final_score: 80, passed: true }),
    });
    socket.close();
    await endAudio();

    expect(states.some((state) => state.phase === "connection-lost")).toBe(false);
    expect(states.at(-1)?.phase).toBe("ended");
  });

  it("uma mensagem de erro so aparece depois que o audio pendente termina", async () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    const states = collectStates(session);
    socket.dispatch("open", {});

    socket.dispatch("message", { data: new ArrayBuffer(4) });
    socket.dispatch("message", { data: JSON.stringify({ type: "error", message: "Falha na transcricao." }) });

    expect(states.at(-1)?.phase).toBe("persona-speaking");

    await endAudio();

    expect(states.at(-1)?.phase).toBe("error");
    expect(states.at(-1)?.errorMessage).toBe("Falha na transcricao.");
  });

  it("o codigo do erro chega ao estado quando o servidor o manda", () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    const states = collectStates(session);
    socket.dispatch("open", {});

    socket.dispatch("message", {
      data: JSON.stringify({
        type: "error",
        message: "O provedor de IA atingiu o limite de uso.",
        code: "provider_rate_limited",
      }),
    });

    expect(states.at(-1)?.phase).toBe("error");
    expect(states.at(-1)?.errorCode).toBe("provider_rate_limited");
  });

  it("o tempo de espera de uma recusa chega ao estado junto com o codigo", () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    const states = collectStates(session);
    socket.dispatch("open", {});

    socket.dispatch("message", {
      data: JSON.stringify({
        type: "error",
        message: "O nivel ainda esta no intervalo entre tentativas.",
        code: "level_in_cooldown",
        retry_after_seconds: 36300,
      }),
    });

    expect(states.at(-1)?.errorCode).toBe("level_in_cooldown");
    expect(states.at(-1)?.errorRetryAfterSeconds).toBe(36300);
  });

  it("uma recusa sem tempo de espera deixa o estado sem tempo", () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    const states = collectStates(session);
    socket.dispatch("open", {});

    socket.dispatch("message", {
      data: JSON.stringify({ type: "error", message: "x", code: "scenario_locked" }),
    });

    expect(states.at(-1)?.errorRetryAfterSeconds).toBeNull();
  });

  it("um erro sem codigo deixa o codigo nulo", () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    const states = collectStates(session);
    socket.dispatch("open", {});

    socket.dispatch("message", { data: JSON.stringify({ type: "error", message: "Token invalido." }) });

    expect(states.at(-1)?.phase).toBe("error");
    expect(states.at(-1)?.errorCode).toBeNull();
  });
});

class FakeMediaRecorder {
  state: "inactive" | "recording" = "inactive";
  readonly mimeType = "audio/webm";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;

  start(): void {
    this.state = "recording";
  }

  stop(): void {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["fala"]) });
    this.onstop?.();
  }
}

const HINT_REQUEST = JSON.stringify({ type: "hint_request" });
const AUTH_MESSAGE = JSON.stringify({ type: "auth", token: "fake-token" });

async function studentTurn(hintsEnabled: boolean) {
  const session = new LiveSession("negociar-prazo", 3, hintsEnabled);
  const socket = FakeWebSocket.instances[0];
  const states = collectStates(session);
  socket.dispatch("open", {});
  socket.dispatch("message", { data: new ArrayBuffer(4) });
  await endAudio();
  return { session, socket, states };
}

describe("LiveSession e a autenticacao da conexao", () => {
  it("a URL da conexao nunca leva o token", () => {
    new LiveSession("negociar-prazo", 3);
    new LiveSession("negociar-prazo", 3, true);

    for (const socket of FakeWebSocket.instances) {
      expect(socket.url).not.toContain("token");
      expect(socket.url).not.toContain("fake-token");
    }
  });

  it("a primeira mensagem, ao abrir a conexao, e a autenticacao com o token atual", () => {
    new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];

    expect(socket.sent).toEqual([]);
    socket.dispatch("open", {});

    expect(socket.sent).toEqual([AUTH_MESSAGE]);
  });

  it("nenhum audio sai antes da autenticacao", () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];

    session.startRecording();
    socket.dispatch("open", {});

    expect(socket.sent[0]).toBe(AUTH_MESSAGE);
    expect(socket.sent.filter((message) => message instanceof ArrayBuffer)).toEqual([]);
  });
});

describe("LiveSession com dicas", () => {
  it("so liga as dicas na URL quando o aluno escolheu no briefing", () => {
    new LiveSession("negociar-prazo", 3, true);
    new LiveSession("negociar-prazo", 3);

    expect(FakeWebSocket.instances[0].url).toContain("?hints=1");
    expect(FakeWebSocket.instances[1].url).not.toContain("hints");
  });

  it("pede a dica uma vez por vez e mostra a dica recebida", async () => {
    const { session, socket, states } = await studentTurn(true);
    expect(states.at(-1)?.phase).toBe("student-turn");

    session.requestHint();
    session.requestHint();

    expect(socket.sent).toEqual([AUTH_MESSAGE, HINT_REQUEST]);
    expect(states.at(-1)?.hint).toEqual({ status: "loading", text: null });

    socket.dispatch("message", { data: JSON.stringify({ type: "hint", text: "Sim, trabalhei em equipe." }) });
    session.requestHint();

    expect(states.at(-1)?.hint).toEqual({ status: "shown", text: "Sim, trabalhei em equipe." });
    expect(socket.sent).toEqual([AUTH_MESSAGE, HINT_REQUEST]);
  });

  it("sem as dicas ligadas, pedir uma dica nao envia nada", async () => {
    const { session, socket, states } = await studentTurn(false);

    session.requestHint();

    expect(socket.sent).toEqual([AUTH_MESSAGE]);
    expect(states.at(-1)?.hint.status).toBe("idle");
  });

  it("fora da vez do aluno, pedir uma dica nao envia nada", () => {
    const session = new LiveSession("negociar-prazo", 3, true);
    const socket = FakeWebSocket.instances[0];
    socket.dispatch("open", {});

    session.requestHint();

    expect(socket.sent).toEqual([AUTH_MESSAGE]);
  });

  it("uma dica indisponivel e informada e pode ser pedida de novo", async () => {
    const { session, socket, states } = await studentTurn(true);

    session.requestHint();
    socket.dispatch("message", { data: JSON.stringify({ type: "hint_unavailable" }) });

    expect(states.at(-1)?.hint).toEqual({ status: "unavailable", text: null });

    session.requestHint();

    expect(socket.sent).toEqual([AUTH_MESSAGE, HINT_REQUEST, HINT_REQUEST]);
  });

  it("a dica some quando o aluno envia a resposta", async () => {
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
    vi.stubGlobal("navigator", {
      mediaDevices: { getUserMedia: async () => ({ getTracks: () => [] }) },
    });
    const { session, socket, states } = await studentTurn(true);
    session.requestHint();
    socket.dispatch("message", { data: JSON.stringify({ type: "hint", text: "Sim." }) });

    vi.useFakeTimers({ toFake: ["Date"] });
    await session.startRecording();
    expect(states.at(-1)?.hint.status).toBe("shown");
    vi.advanceTimersByTime(800);
    session.stopRecording();
    await new Promise((resolve) => setTimeout(resolve, 0));
    vi.useRealTimers();

    expect(states.at(-1)?.phase).toBe("persona-speaking");
    expect(states.at(-1)?.hint).toEqual({ status: "idle", text: null });
    expect(socket.sent.at(-1)).toBeInstanceOf(ArrayBuffer);
  });
});


describe("LiveSession e o player das falas", () => {
  function microphone(onOpen: () => void = () => undefined) {
    const getUserMedia = vi.fn(async () => {
      onOpen();
      return { getTracks: () => [{ stop: vi.fn() }] };
    });
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    return getUserMedia;
  }

  it("segurar para falar libera o player antes de abrir o microfone", async () => {
    let playedWhenMicrophoneOpened: string[] = [];
    microphone(() => {
      playedWhenMicrophoneOpened = [...player().played];
    });
    const { session } = await studentTurn(false);

    await session.startRecording();

    expect(playedWhenMicrophoneOpened).toContain("blob:silence");
  });

  it("o silêncio de liberação não é uma fala: não entra na fila nem muda a vez", async () => {
    microphone();
    const { session, states } = await studentTurn(false);
    const spokenBefore = spokenLines().length;

    await session.startRecording();

    expect(spokenLines()).toHaveLength(spokenBefore);
    expect(states.at(-1)?.phase).toBe("recording");
    expect(states.at(-1)?.turnCount).toBe(1);
  });

  it("toca a fala seguinte sozinha, no mesmo player que foi liberado", async () => {
    microphone();
    const { session, socket } = await studentTurn(false);
    await session.startRecording();
    const elementsBefore = FakeAudio.instances.length;

    socket.dispatch("message", { data: new ArrayBuffer(4) });

    expect(FakeAudio.instances).toHaveLength(elementsBefore);
    expect(spokenLines()).toHaveLength(2);
  });

  it("não libera o player no meio de uma fala da persona", async () => {
    microphone();
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    socket.dispatch("open", {});
    socket.dispatch("message", { data: new ArrayBuffer(4) });

    await session.startRecording();

    expect(player().played.filter((src) => src === "blob:silence")).toHaveLength(0);
  });
});

describe("LiveSession gravando a fala do aluno", () => {
  function microphone() {
    const stopTrack = vi.fn();
    const getUserMedia = vi.fn(async () => ({ getTracks: () => [{ stop: stopTrack }] }));
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    return { stopTrack, getUserMedia };
  }

  it("uma gravação curta demais não é enviada, e o aluno é avisado de que não foi ouvido", async () => {
    microphone();
    const { session, socket, states } = await studentTurn(false);

    await session.startRecording();
    session.stopRecording();
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(socket.sent.some((message) => message instanceof ArrayBuffer)).toBe(false);
    expect(states.at(-1)?.phase).toBe("student-turn");
    expect(states.at(-1)?.noSpeechNotice).toBe(true);
  });

  it("uma gravação longa que saiu sem nenhum áudio não é enviada, e o aluno é avisado", async () => {
    class EmptyMediaRecorder extends FakeMediaRecorder {
      stop(): void {
        this.state = "inactive";
        this.ondataavailable?.({ data: new Blob([]) });
        this.onstop?.();
      }
    }
    const { stopTrack } = microphone();
    vi.stubGlobal("MediaRecorder", EmptyMediaRecorder);
    const { session, socket, states } = await studentTurn(false);

    vi.useFakeTimers({ toFake: ["Date"] });
    await session.startRecording();
    vi.advanceTimersByTime(2000);
    session.stopRecording();
    await new Promise((resolve) => setTimeout(resolve, 0));
    vi.useRealTimers();

    expect(socket.sent.some((message) => message instanceof ArrayBuffer)).toBe(false);
    expect(states.at(-1)?.phase).toBe("student-turn");
    expect(states.at(-1)?.noSpeechNotice).toBe(true);
    expect(stopTrack).toHaveBeenCalledTimes(1);
  });

  it("depois do aviso, o aluno pode gravar de novo e a fala longa é enviada", async () => {
    microphone();
    const { session, socket, states } = await studentTurn(false);
    await session.startRecording();
    session.stopRecording();
    await new Promise((resolve) => setTimeout(resolve, 0));

    vi.useFakeTimers({ toFake: ["Date"] });
    await session.startRecording();
    expect(states.at(-1)?.noSpeechNotice).toBe(false);
    vi.advanceTimersByTime(800);
    session.stopRecording();
    await new Promise((resolve) => setTimeout(resolve, 0));
    vi.useRealTimers();

    expect(socket.sent.at(-1)).toBeInstanceOf(ArrayBuffer);
    expect(states.at(-1)?.phase).toBe("persona-speaking");
  });

  it("soltar o botão antes de o microfone abrir não começa a gravar e avisa o aluno", async () => {
    const { stopTrack } = microphone();
    let openMicrophone: (stream: unknown) => void = () => {};
    navigator.mediaDevices.getUserMedia = vi.fn(
      () =>
        new Promise((resolve) => {
          openMicrophone = resolve as (stream: unknown) => void;
        }),
    ) as never;
    const { session, states } = await studentTurn(false);

    const starting = session.startRecording();
    session.stopRecording();
    openMicrophone({ getTracks: () => [{ stop: stopTrack }] });
    await starting;

    expect(states.at(-1)?.phase).toBe("student-turn");
    expect(states.at(-1)?.noSpeechNotice).toBe(true);
    expect(stopTrack).toHaveBeenCalledTimes(1);
  });

  it("dois toques seguidos abrem um só microfone", async () => {
    const { getUserMedia } = microphone();
    const { session } = await studentTurn(false);

    const first = session.startRecording();
    const second = session.startRecording();
    await Promise.all([first, second]);

    expect(getUserMedia).toHaveBeenCalledTimes(1);
  });
});
