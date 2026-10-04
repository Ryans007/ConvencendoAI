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
    for (const listener of this.listeners[type] ?? []) {
      listener(event);
    }
  }
}

class FakeAudio {
  static instances: FakeAudio[] = [];
  static nextPlayRejects = false;
  readonly src: string;
  private endedListener: (() => void) | null = null;

  constructor(src: string) {
    this.src = src;
    FakeAudio.instances.push(this);
  }

  addEventListener(type: string, listener: () => void): void {
    if (type === "ended") {
      this.endedListener = listener;
    }
  }

  play(): Promise<void> {
    if (FakeAudio.nextPlayRejects) {
      FakeAudio.nextPlayRejects = false;
      return Promise.reject(new Error("NotAllowedError"));
    }
    return Promise.resolve();
  }

  triggerEnded(): void {
    this.endedListener?.();
  }
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
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:fake" }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("services/liveSession", () => {
  it("toca o audio das personas em sequencia, nunca dois ao mesmo tempo", () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    socket.dispatch("open", {});

    socket.dispatch("message", { data: new ArrayBuffer(4) });
    socket.dispatch("message", { data: new ArrayBuffer(4) });

    expect(FakeAudio.instances).toHaveLength(1);

    FakeAudio.instances[0].triggerEnded();
    expect(FakeAudio.instances).toHaveLength(2);

    const states = collectStates(session);
    FakeAudio.instances[1].triggerEnded();

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

    errorSpy.mockRestore();
  });

  it("so resolve o fim de sessao depois que o ultimo audio termina de tocar", () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    const states = collectStates(session);
    socket.dispatch("open", {});

    socket.dispatch("message", { data: new ArrayBuffer(4) });
    socket.dispatch("message", {
      data: JSON.stringify({ type: "session_ended", attempt_id: 42, final_score: 90, passed: true }),
    });

    expect(states.at(-1)?.phase).toBe("persona-speaking");

    FakeAudio.instances[0].triggerEnded();

    expect(states.at(-1)?.phase).toBe("ended");
    expect(states.at(-1)?.result).toEqual({ attemptId: 42, finalScore: 90, passed: true });
  });

  it("sem fala detectada, devolve a vez ao aluno com aviso e sem contar turno", () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    const states = collectStates(session);
    socket.dispatch("open", {});

    socket.dispatch("message", { data: new ArrayBuffer(4) });
    FakeAudio.instances[0].triggerEnded();
    expect(states.at(-1)?.turnCount).toBe(1);

    socket.dispatch("message", { data: JSON.stringify({ type: "no_speech" }) });

    expect(states.at(-1)?.phase).toBe("student-turn");
    expect(states.at(-1)?.noSpeechNotice).toBe(true);
    expect(states.at(-1)?.turnCount).toBe(1);
  });

  it("depois do aviso de avaliacao, o fim do audio leva a fase de avaliacao, e nao a vez do aluno", () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    const states = collectStates(session);
    socket.dispatch("open", {});

    socket.dispatch("message", { data: new ArrayBuffer(4) });
    socket.dispatch("message", { data: JSON.stringify({ type: "evaluating" }) });
    FakeAudio.instances[0].triggerEnded();

    expect(states.at(-1)?.phase).toBe("evaluating");
    expect(states.some((state) => state.phase === "student-turn")).toBe(false);

    socket.dispatch("message", {
      data: JSON.stringify({ type: "session_ended", attempt_id: 7, final_score: 80, passed: true }),
    });

    expect(states.at(-1)?.phase).toBe("ended");
    expect(states.at(-1)?.result).toEqual({ attemptId: 7, finalScore: 80, passed: true });
  });

  it("o fechamento logo apos o fim de sessao nao vira conexao perdida enquanto o audio toca", () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    const states = collectStates(session);
    socket.dispatch("open", {});

    socket.dispatch("message", { data: new ArrayBuffer(4) });
    socket.dispatch("message", {
      data: JSON.stringify({ type: "session_ended", attempt_id: 7, final_score: 80, passed: true }),
    });
    socket.close();
    FakeAudio.instances[0].triggerEnded();

    expect(states.some((state) => state.phase === "connection-lost")).toBe(false);
    expect(states.at(-1)?.phase).toBe("ended");
  });

  it("uma mensagem de erro so aparece depois que o audio pendente termina", () => {
    const session = new LiveSession("negociar-prazo", 3);
    const socket = FakeWebSocket.instances[0];
    const states = collectStates(session);
    socket.dispatch("open", {});

    socket.dispatch("message", { data: new ArrayBuffer(4) });
    socket.dispatch("message", { data: JSON.stringify({ type: "error", message: "Falha na transcricao." }) });

    expect(states.at(-1)?.phase).toBe("persona-speaking");

    FakeAudio.instances[0].triggerEnded();

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

function studentTurn(hintsEnabled: boolean) {
  const session = new LiveSession("negociar-prazo", 3, hintsEnabled);
  const socket = FakeWebSocket.instances[0];
  const states = collectStates(session);
  socket.dispatch("open", {});
  socket.dispatch("message", { data: new ArrayBuffer(4) });
  FakeAudio.instances[0].triggerEnded();
  return { session, socket, states };
}

describe("LiveSession com dicas", () => {
  it("so liga as dicas na URL quando o aluno escolheu no briefing", () => {
    new LiveSession("negociar-prazo", 3, true);
    new LiveSession("negociar-prazo", 3);

    expect(FakeWebSocket.instances[0].url).toContain("&hints=1");
    expect(FakeWebSocket.instances[1].url).not.toContain("hints");
  });

  it("pede a dica uma vez por vez e mostra a dica recebida", () => {
    const { session, socket, states } = studentTurn(true);
    expect(states.at(-1)?.phase).toBe("student-turn");

    session.requestHint();
    session.requestHint();

    expect(socket.sent).toEqual([HINT_REQUEST]);
    expect(states.at(-1)?.hint).toEqual({ status: "loading", text: null });

    socket.dispatch("message", { data: JSON.stringify({ type: "hint", text: "Sim, trabalhei em equipe." }) });
    session.requestHint();

    expect(states.at(-1)?.hint).toEqual({ status: "shown", text: "Sim, trabalhei em equipe." });
    expect(socket.sent).toEqual([HINT_REQUEST]);
  });

  it("sem as dicas ligadas, pedir uma dica nao envia nada", () => {
    const { session, socket, states } = studentTurn(false);

    session.requestHint();

    expect(socket.sent).toEqual([]);
    expect(states.at(-1)?.hint.status).toBe("idle");
  });

  it("fora da vez do aluno, pedir uma dica nao envia nada", () => {
    const session = new LiveSession("negociar-prazo", 3, true);
    const socket = FakeWebSocket.instances[0];
    socket.dispatch("open", {});

    session.requestHint();

    expect(socket.sent).toEqual([]);
  });

  it("uma dica indisponivel e informada e pode ser pedida de novo", () => {
    const { session, socket, states } = studentTurn(true);

    session.requestHint();
    socket.dispatch("message", { data: JSON.stringify({ type: "hint_unavailable" }) });

    expect(states.at(-1)?.hint).toEqual({ status: "unavailable", text: null });

    session.requestHint();

    expect(socket.sent).toEqual([HINT_REQUEST, HINT_REQUEST]);
  });

  it("a dica some quando o aluno envia a resposta", async () => {
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
    vi.stubGlobal("navigator", {
      mediaDevices: { getUserMedia: async () => ({ getTracks: () => [] }) },
    });
    const { session, socket, states } = studentTurn(true);
    session.requestHint();
    socket.dispatch("message", { data: JSON.stringify({ type: "hint", text: "Sim." }) });

    await session.startRecording();
    expect(states.at(-1)?.hint.status).toBe("shown");
    session.stopRecording();
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(states.at(-1)?.phase).toBe("persona-speaking");
    expect(states.at(-1)?.hint).toEqual({ status: "idle", text: null });
    expect(socket.sent.at(-1)).toBeInstanceOf(ArrayBuffer);
  });
});
