import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AudioRecorder } from "./audioRecorder";

class FakeMediaRecorder {
  state: "inactive" | "recording" = "inactive";
  readonly mimeType: string = "audio/webm;codecs=opus";
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

const stopTrack = vi.fn();

beforeEach(() => {
  vi.useFakeTimers();
  stopTrack.mockClear();
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  vi.stubGlobal("navigator", {
    mediaDevices: { getUserMedia: async () => ({ getTracks: () => [{ stop: stopTrack }] }) },
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("AudioRecorder", () => {
  it("entrega o áudio gravado, com o tipo e a duração", async () => {
    const recorder = new AudioRecorder();

    await recorder.start();
    vi.advanceTimersByTime(1200);
    const recording = await recorder.stop();

    expect(recording?.durationMs).toBe(1200);
    expect(recording?.blob.type).toBe("audio/webm;codecs=opus");
    expect(await recording?.blob.text()).toBe("fala");
  });

  it("solta o microfone ao terminar a gravação", async () => {
    const recorder = new AudioRecorder();

    await recorder.start();
    await recorder.stop();

    expect(stopTrack).toHaveBeenCalledTimes(1);
  });

  it("sem gravação em curso, parar devolve null", async () => {
    const recorder = new AudioRecorder();

    expect(await recorder.stop()).toBeNull();
  });

  it("parar duas vezes só entrega a gravação uma vez", async () => {
    const recorder = new AudioRecorder();
    await recorder.start();

    const first = await recorder.stop();
    const second = await recorder.stop();

    expect(first).not.toBeNull();
    expect(second).toBeNull();
  });

  it("soltar no meio da gravação libera o microfone e descarta o áudio", async () => {
    const recorder = new AudioRecorder();
    await recorder.start();

    recorder.release();

    expect(stopTrack).toHaveBeenCalledTimes(1);
    expect(await recorder.stop()).toBeNull();
  });

  it("uma nova gravação começa sem os pedaços da anterior", async () => {
    const recorder = new AudioRecorder();
    await recorder.start();
    await recorder.stop();

    await recorder.start();
    const recording = await recorder.stop();

    expect(await recording?.blob.text()).toBe("fala");
  });
});
