import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AudioRecorder, MIN_RECORDING_MS } from "./audioRecorder";

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

  it("a duração mínima que vale como fala é de 350 ms", () => {
    expect(MIN_RECORDING_MS).toBe(350);
  });

  it("fica ocupado enquanto grava e livre depois de parar", async () => {
    const recorder = new AudioRecorder();
    expect(recorder.active).toBe(false);

    await recorder.start();
    expect(recorder.active).toBe(true);

    await recorder.stop();
    expect(recorder.active).toBe(false);
  });

  it("um segundo start enquanto grava é ignorado e não abre outro microfone", async () => {
    const getUserMedia = vi.fn(async () => ({ getTracks: () => [{ stop: stopTrack }] }));
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    const recorder = new AudioRecorder();

    const first = await recorder.start();
    const second = await recorder.start();
    await recorder.stop();

    expect([first, second]).toEqual([true, false]);
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(stopTrack).toHaveBeenCalledTimes(1);
  });

  it("dois start seguidos, sem esperar, abrem um só microfone", async () => {
    const getUserMedia = vi.fn(async () => ({ getTracks: () => [{ stop: stopTrack }] }));
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    const recorder = new AudioRecorder();

    const results = await Promise.all([recorder.start(), recorder.start()]);
    await recorder.stop();

    expect(results).toEqual([true, false]);
    expect(getUserMedia).toHaveBeenCalledTimes(1);
  });

  it("parar antes de o microfone abrir cancela a gravação e solta o microfone", async () => {
    let openMicrophone: (stream: unknown) => void = () => {};
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: () =>
          new Promise((resolve) => {
            openMicrophone = resolve;
          }),
      },
    });
    const recorder = new AudioRecorder();

    const starting = recorder.start();
    const stopped = await recorder.stop();
    openMicrophone({ getTracks: () => [{ stop: stopTrack }] });

    expect(stopped).toBeNull();
    expect(await starting).toBe(false);
    expect(stopTrack).toHaveBeenCalledTimes(1);
    expect(recorder.active).toBe(false);
  });

  it("depois de um cancelamento, o aluno consegue gravar normalmente", async () => {
    let openMicrophone: (stream: unknown) => void = () => {};
    const getUserMedia = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            openMicrophone = resolve;
          }),
      )
      .mockImplementation(async () => ({ getTracks: () => [{ stop: stopTrack }] }));
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    const recorder = new AudioRecorder();
    const cancelled = recorder.start();
    await recorder.stop();
    openMicrophone({ getTracks: () => [{ stop: stopTrack }] });
    await cancelled;

    expect(await recorder.start()).toBe(true);
    vi.advanceTimersByTime(500);
    expect((await recorder.stop())?.durationMs).toBe(500);
  });

  it("soltar o gravador enquanto o microfone abre também cancela", async () => {
    let openMicrophone: (stream: unknown) => void = () => {};
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: () =>
          new Promise((resolve) => {
            openMicrophone = resolve;
          }),
      },
    });
    const recorder = new AudioRecorder();

    const starting = recorder.start();
    recorder.release();
    openMicrophone({ getTracks: () => [{ stop: stopTrack }] });

    expect(await starting).toBe(false);
    expect(stopTrack).toHaveBeenCalledTimes(1);
  });

  it("se o aluno nega o microfone, o gravador falha e continua livre para tentar de novo", async () => {
    const getUserMedia = vi
      .fn()
      .mockRejectedValueOnce(new DOMException("negado", "NotAllowedError"))
      .mockImplementation(async () => ({ getTracks: () => [{ stop: stopTrack }] }));
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    const recorder = new AudioRecorder();

    await expect(recorder.start()).rejects.toThrow("negado");

    expect(recorder.active).toBe(false);
    expect(await recorder.start()).toBe(true);
  });

  it("se o navegador não consegue criar o gravador, o microfone é solto", async () => {
    vi.stubGlobal("MediaRecorder", function BrokenMediaRecorder() {
      throw new Error("sem suporte");
    });
    const recorder = new AudioRecorder();

    await expect(recorder.start()).rejects.toThrow("sem suporte");

    expect(stopTrack).toHaveBeenCalledTimes(1);
    expect(recorder.active).toBe(false);
  });
});
