import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { activeSpeechContext, releaseSpeechAudio, unlockSpeechAudio } from "./speechAudio";
import { FakeContext } from "./testing/fakeAudioContext";

class FakeSilentAudio {
  static instances: FakeSilentAudio[] = [];
  src = "";
  played = 0;

  constructor() {
    FakeSilentAudio.instances.push(this);
  }

  play(): Promise<void> {
    this.played += 1;
    return Promise.resolve();
  }
}

let created: FakeContext[] = [];

class RecordingContext extends FakeContext {
  constructor(options?: { sampleRate?: number }) {
    super(options);
    created.push(this);
  }
}

beforeEach(() => {
  created = [];
  FakeSilentAudio.instances = [];
  vi.stubGlobal("AudioContext", RecordingContext);
  vi.stubGlobal("Audio", FakeSilentAudio);
  vi.stubGlobal(
    "URL",
    Object.assign(URL, { createObjectURL: () => "blob:silence", revokeObjectURL: () => undefined }),
  );
});

afterEach(() => {
  releaseSpeechAudio();
  vi.unstubAllGlobals();
});

describe("services/speechAudio", () => {
  it("sem ter sido liberado, nao ha contexto ativo", () => {
    expect(activeSpeechContext()).toBeNull();
  });

  it("liberar cria um contexto na taxa do audio da fala e o retoma", async () => {
    unlockSpeechAudio();
    await Promise.resolve();

    expect(created).toHaveLength(1);
    expect(created[0].options).toEqual({ sampleRate: 24000 });
    expect(activeSpeechContext()).toBe(created[0]);
  });

  it("liberar de novo reaproveita o mesmo contexto, e nao cria um por fala", async () => {
    unlockSpeechAudio();
    unlockSpeechAudio();
    unlockSpeechAudio();
    await Promise.resolve();

    expect(created).toHaveLength(1);
  });

  it("toca um instante de silencio num elemento de audio, para o som sair com a chavinha de silencioso", () => {
    unlockSpeechAudio();

    expect(FakeSilentAudio.instances).toHaveLength(1);
    expect(FakeSilentAudio.instances[0].played).toBe(1);
  });

  it("um contexto suspenso nao conta como ativo", () => {
    unlockSpeechAudio();
    created[0].state = "suspended";

    expect(activeSpeechContext()).toBeNull();
  });

  it("o estado interrompido do iPhone nao conta como ativo", () => {
    unlockSpeechAudio();
    created[0].state = "interrupted";

    expect(activeSpeechContext()).toBeNull();
  });

  it("um aparelho sem WebAudio fica sem contexto e sem erro", () => {
    vi.stubGlobal("AudioContext", undefined);

    expect(() => unlockSpeechAudio()).not.toThrow();
    expect(activeSpeechContext()).toBeNull();
  });

  it("depois de fechado, liberar de novo cria um contexto novo", async () => {
    unlockSpeechAudio();
    await Promise.resolve();
    created[0].state = "closed";

    unlockSpeechAudio();
    await Promise.resolve();

    expect(created).toHaveLength(2);
    expect(activeSpeechContext()).toBe(created[1]);
  });

  it("um aparelho que recusa a taxa pedida usa a taxa padrao", async () => {
    let attempts = 0;
    class PickyContext extends FakeContext {
      constructor(options?: { sampleRate?: number }) {
        attempts += 1;
        if (options?.sampleRate) {
          throw new Error("taxa nao suportada");
        }
        super(options);
        created.push(this);
      }
    }
    vi.stubGlobal("AudioContext", PickyContext);

    unlockSpeechAudio();
    await Promise.resolve();

    expect(attempts).toBe(2);
    expect(activeSpeechContext()).toBe(created[0]);
  });
});
