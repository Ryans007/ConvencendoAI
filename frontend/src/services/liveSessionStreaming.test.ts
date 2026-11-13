import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LiveSession, type LiveSessionState } from "./liveSession";
import { releaseSpeechAudio, unlockSpeechAudio } from "./speechAudio";
import { FakeContext } from "./testing/fakeAudioContext";

vi.mock("./session", () => ({
  getAccessToken: () => "fake-token",
}));

const RATE = 24000;

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
  src = "";
  error: Error | null = null;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onplaying: (() => void) | null = null;
  readonly played: string[] = [];

  constructor() {
    FakeAudio.instances.push(this);
  }

  play(): Promise<void> {
    this.played.push(this.src);
    return Promise.resolve();
  }
}

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

let contexts: FakeContext[] = [];

class RecordingContext extends FakeContext {
  constructor(options?: { sampleRate?: number }) {
    super(options);
    contexts.push(this);
  }
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  FakeAudio.instances = [];
  contexts = [];
  let blobs = 0;
  vi.stubGlobal("WebSocket", FakeWebSocket);
  vi.stubGlobal("Audio", FakeAudio);
  vi.stubGlobal("AudioContext", RecordingContext);
  vi.stubGlobal("location", { protocol: "https:", host: "app.exemplo.com.br" });
  vi.stubGlobal(
    "URL",
    Object.assign(URL, {
      createObjectURL: (blob: Blob) =>
        blob.size === 1644 ? "blob:silence" : `blob:fake-${(blobs += 1)}`,
      revokeObjectURL: () => undefined,
    }),
  );
});

afterEach(() => {
  releaseSpeechAudio();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function collect(session: LiveSession): LiveSessionState[] {
  const states: LiveSessionState[] = [];
  session.subscribe((state) => states.push(state));
  return states;
}

function open(options: { unlocked?: boolean } = {}) {
  if (options.unlocked !== false) {
    unlockSpeechAudio();
  }
  const session = new LiveSession("negociar-prazo", 3, false);
  const socket = FakeWebSocket.instances[0];
  const states = collect(session);
  socket.dispatch("open", {});
  return { session, socket, states, context: contexts[0] };
}

function control(socket: FakeWebSocket, payload: Record<string, unknown>): void {
  socket.dispatch("message", { data: JSON.stringify(payload) });
}

function chunk(socket: FakeWebSocket, seconds: number): number {
  const bytes = Math.round(seconds * RATE) * 2;
  socket.dispatch("message", { data: new ArrayBuffer(bytes) });
  return bytes;
}

function speak(
  socket: FakeWebSocket,
  name: string,
  seconds: number,
  options: { finish?: boolean; declaredExtra?: number } = {},
): number {
  control(socket, { type: "speaker", name });
  control(socket, { type: "speech_start", format: "pcm_s16le", sample_rate: RATE, channels: 1 });
  let total = 0;
  for (let piece = 0; piece < Math.round(seconds / 0.2); piece += 1) {
    total += chunk(socket, 0.2);
  }
  if (options.finish !== false) {
    control(socket, { type: "speech_end", bytes: total + (options.declaredExtra ?? 0) });
  }
  return total;
}

async function settle(): Promise<void> {
  for (let turn = 0; turn < 5; turn += 1) {
    await Promise.resolve();
  }
}

function sentMessages(socket: FakeWebSocket): Array<Record<string, unknown>> {
  return socket.sent
    .filter((message): message is string => typeof message === "string")
    .map((message) => JSON.parse(message));
}

function microphone(): void {
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  vi.stubGlobal("navigator", {
    mediaDevices: { getUserMedia: async () => ({ getTracks: () => [{ stop: vi.fn() }] }) },
  });
}

describe("LiveSession e a fala em fluxo, declarando o suporte", () => {
  it("declara stream_audio na autenticacao quando o contexto de audio esta ativo", () => {
    const { socket } = open();

    expect(sentMessages(socket)[0]).toEqual({
      type: "auth",
      token: "fake-token",
      stream_audio: true,
    });
  });

  it("nao declara quando o aparelho nao liberou o contexto de audio", () => {
    const { socket } = open({ unlocked: false });

    expect(sentMessages(socket)[0]).toEqual({ type: "auth", token: "fake-token" });
  });

  it("nao declara quando o contexto foi liberado mas nao esta tocando", () => {
    unlockSpeechAudio();
    contexts[0].state = "suspended";
    const session = new LiveSession("negociar-prazo", 3, false);
    const socket = FakeWebSocket.instances[0];
    socket.dispatch("open", {});

    expect(session).toBeDefined();
    expect(sentMessages(socket)[0]).toEqual({ type: "auth", token: "fake-token" });
  });
});

describe("LiveSession tocando a fala em fluxo", () => {
  it("mostra o nome de quem fala logo, e so conta como tocando quando o primeiro som comeca", () => {
    const { socket, states } = open();

    control(socket, { type: "speaker", name: "Rachel" });
    control(socket, { type: "speech_start", format: "pcm_s16le", sample_rate: RATE, channels: 1 });

    expect(states.at(-1)?.speakerName).toBe("Rachel");
    expect(states.at(-1)?.personaAudible).toBe(false);

    for (let piece = 0; piece < 4; piece += 1) {
      chunk(socket, 0.2);
    }

    expect(states.at(-1)?.personaAudible).toBe(true);
  });

  it("devolve a vez ao aluno so quando o ultimo som termina", async () => {
    const { socket, states, context } = open();

    speak(socket, "Rachel", 1.0);
    await settle();
    expect(states.at(-1)?.phase).toBe("persona-speaking");

    context.advance(10);
    await settle();

    expect(states.at(-1)?.phase).toBe("student-turn");
    expect(states.at(-1)?.personaAudible).toBe(false);
  });

  it("a segunda fala so comeca a tocar depois do fim da primeira, e com o nome dela", async () => {
    const { socket, states, context } = open();

    speak(socket, "Rachel", 1.0);
    speak(socket, "Tom", 1.0);
    const scheduledForTheFirst = context.sources.length;
    await settle();

    expect(scheduledForTheFirst).toBeGreaterThan(0);
    expect(states.at(-1)?.speakerName).toBe("Rachel");

    context.advance(10);
    await settle();

    expect(context.sources.length).toBeGreaterThan(scheduledForTheFirst);
    expect(states.map((state) => state.speakerName)).toContain("Tom");
  });

  it("um quadro binario fora de uma fala em fluxo toca como fala inteira, pelo player de antes", async () => {
    const { socket } = open();

    socket.dispatch("message", { data: new ArrayBuffer(4) });
    await settle();

    const spoken = FakeAudio.instances.at(-1)?.played.filter((src) => src !== "blob:silence") ?? [];
    expect(spoken).toHaveLength(1);
    expect(context(0).sources).toHaveLength(0);
  });

  it("uma fala que chega menor que o fim declarado e avisada ao servidor com os dois totais", async () => {
    const { socket, context } = open();

    const received = speak(socket, "Rachel", 1.0, { declaredExtra: 5000 });
    context.advance(10);
    await settle();

    expect(sentMessages(socket)).toContainEqual({
      type: "speech_cut",
      expected_bytes: received + 5000,
      received_bytes: received,
    });
  });

  it("uma fala inteira nao manda nenhum aviso de corte", async () => {
    const { socket, context } = open();

    speak(socket, "Rachel", 1.0);
    context.advance(10);
    await settle();

    expect(sentMessages(socket).some((message) => message.type === "speech_cut")).toBe(false);
  });

  it("a conexao que cai no meio da fala nao quebra e leva a conexao perdida", async () => {
    const { socket, states, context } = open();

    speak(socket, "Rachel", 1.0, { finish: false });
    socket.close();
    context.advance(10);
    await settle();

    expect(states.at(-1)?.phase).toBe("connection-lost");
  });

  it("sair da tela no meio de uma fala interrompe o som e nao deixa a proxima comecar", async () => {
    const { session, socket, context } = open();

    speak(socket, "Rachel", 1.0);
    speak(socket, "Tom", 1.0);
    const before = context.sources.length;
    session.dispose();
    context.advance(10);
    await settle();

    expect(context.sources.every((source) => source.stopped)).toBe(true);
    expect(context.sources).toHaveLength(before);
  });

  it("uma fala em fluxo que o aparelho nao esta preparado para tocar e descartada e avisada", async () => {
    const { socket } = open({ unlocked: false });

    control(socket, { type: "speaker", name: "Rachel" });
    control(socket, { type: "speech_start", format: "pcm_s16le", sample_rate: RATE, channels: 1 });
    chunk(socket, 0.5);
    control(socket, { type: "speech_end", bytes: Math.round(0.5 * RATE) * 2 });
    await settle();

    expect(sentMessages(socket)).toContainEqual({
      type: "playback_failed",
      reason: "NoSpeechContext",
    });
    expect(FakeAudio.instances.at(-1)?.played.filter((src) => src !== "blob:silence") ?? []).toHaveLength(0);
  });
});

describe("LiveSession e a latencia da fala em fluxo", () => {
  async function respondedStudentTurn() {
    microphone();
    vi.useFakeTimers({ toFake: ["Date"] });
    const opened = open();
    speak(opened.socket, "Rachel", 1.0);
    opened.context.advance(10);
    await settle();
    await opened.session.startRecording();
    vi.advanceTimersByTime(800);
    opened.session.stopRecording();
    await new Promise((resolve) => setTimeout(resolve, 0));
    return opened;
  }

  it("espera a fila esvaziar para reportar, e leva os esvaziamentos e as falas cortadas da vez", async () => {
    const { socket, context } = await respondedStudentTurn();
    vi.advanceTimersByTime(2100);

    speak(socket, "Rachel", 1.0);
    expect(sentMessages(socket).some((message) => message.type === "turn_latency")).toBe(false);

    context.advance(10);
    await settle();

    expect(sentMessages(socket).filter((message) => message.type === "turn_latency")).toEqual([
      { type: "turn_latency", total_ms: 2100, underruns: 0, cut_lines: 0 },
    ]);
  });

  it("conta a fala cortada da vez na mesma mensagem de latencia", async () => {
    const { socket, context } = await respondedStudentTurn();
    vi.advanceTimersByTime(900);

    speak(socket, "Rachel", 1.0, { declaredExtra: 100 });
    context.advance(10);
    await settle();

    expect(sentMessages(socket).filter((message) => message.type === "turn_latency")).toEqual([
      { type: "turn_latency", total_ms: 900, underruns: 0, cut_lines: 1 },
    ]);
  });
});

function context(index: number): FakeContext {
  return contexts[index];
}
