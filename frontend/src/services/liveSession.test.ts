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
  private readonly listeners: Record<string, Array<(event: unknown) => void>> = {};

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  addEventListener(type: string, listener: (event: unknown) => void): void {
    (this.listeners[type] ??= []).push(listener);
  }

  send(): void {}

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
});
