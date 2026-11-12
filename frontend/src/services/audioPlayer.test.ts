import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AudioPlayer } from "./audioPlayer";

class FakeAudio {
  static instances: FakeAudio[] = [];
  static nextPlayRejectsWith: Error | null = null;
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
    if (FakeAudio.nextPlayRejectsWith) {
      const error = FakeAudio.nextPlayRejectsWith;
      FakeAudio.nextPlayRejectsWith = null;
      return Promise.reject(error);
    }
    return Promise.resolve();
  }
}

const created: Blob[] = [];
const revoked: string[] = [];

beforeEach(() => {
  FakeAudio.instances = [];
  FakeAudio.nextPlayRejectsWith = null;
  created.length = 0;
  revoked.length = 0;
  vi.stubGlobal("Audio", FakeAudio);
  vi.stubGlobal(
    "URL",
    Object.assign(URL, {
      createObjectURL: (blob: Blob) => {
        created.push(blob);
        return `blob:${created.length}`;
      },
      revokeObjectURL: (url: string) => revoked.push(url),
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const speech = () => new Blob(["fala"], { type: "audio/wav" });

describe("AudioPlayer", () => {
  it("destravar toca um silêncio curto, que é um WAV válido de zeros", async () => {
    const player = new AudioPlayer();

    player.unlock();

    const element = FakeAudio.instances[0];
    expect(element.played).toEqual(["blob:1"]);
    const bytes = new Uint8Array(await created[0].arrayBuffer());
    expect(String.fromCharCode(...bytes.slice(0, 4))).toBe("RIFF");
    expect(String.fromCharCode(...bytes.slice(8, 12))).toBe("WAVE");
    expect(bytes.slice(44).every((byte) => byte === 0)).toBe(true);
  });

  it("destravar nunca falha, mesmo que o navegador recuse o silêncio", () => {
    FakeAudio.nextPlayRejectsWith = new DOMException("recusado", "NotAllowedError");
    const player = new AudioPlayer();

    expect(() => player.unlock()).not.toThrow();
  });

  it("destravar de novo reaproveita o mesmo silêncio e o mesmo elemento", () => {
    const player = new AudioPlayer();

    player.unlock();
    player.unlock();

    expect(FakeAudio.instances).toHaveLength(1);
    expect(created).toHaveLength(1);
    expect(FakeAudio.instances[0].played).toEqual(["blob:1", "blob:1"]);
  });

  it("toca o áudio e resolve quando ele termina", async () => {
    const player = new AudioPlayer();
    let finished = false;

    const playing = player.play(speech()).then(() => {
      finished = true;
    });
    await Promise.resolve();
    expect(FakeAudio.instances[0].played).toEqual(["blob:1"]);
    expect(finished).toBe(false);

    FakeAudio.instances[0].onended?.();
    await playing;

    expect(finished).toBe(true);
  });

  it("varias falas usam o mesmo elemento", async () => {
    const player = new AudioPlayer();

    const first = player.play(speech());
    FakeAudio.instances[0].onended?.();
    await first;
    const second = player.play(speech());
    FakeAudio.instances[0].onended?.();
    await second;

    expect(FakeAudio.instances).toHaveLength(1);
    expect(FakeAudio.instances[0].played).toEqual(["blob:1", "blob:2"]);
  });

  it("recusa de reprodução rejeita com o erro original", async () => {
    const refusal = new DOMException("recusado", "NotAllowedError");
    FakeAudio.nextPlayRejectsWith = refusal;
    const player = new AudioPlayer();

    await expect(player.play(speech())).rejects.toBe(refusal);
  });

  it("falha do elemento rejeita com o erro de mídia dele", async () => {
    const player = new AudioPlayer();
    const playing = player.play(speech());
    const mediaError = new Error("decodificação");
    FakeAudio.instances[0].error = mediaError;

    FakeAudio.instances[0].onerror?.();

    await expect(playing).rejects.toBe(mediaError);
  });

  it("solta a URL da fala anterior ao tocar a próxima", async () => {
    const player = new AudioPlayer();
    const first = player.play(speech());
    FakeAudio.instances[0].onended?.();
    await first;

    void player.play(speech());

    expect(revoked).toEqual(["blob:1"]);
  });

  it("avisa o início do som uma só vez, quando o navegador começa a tocar", () => {
    const player = new AudioPlayer();
    const onStart = vi.fn();

    void player.play(speech(), onStart);
    expect(onStart).not.toHaveBeenCalled();
    const element = FakeAudio.instances[0];
    element.onplaying?.();
    element.onplaying?.();

    expect(onStart).toHaveBeenCalledTimes(1);
  });
});
