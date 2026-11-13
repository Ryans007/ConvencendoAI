import { describe, expect, it, vi } from "vitest";

import { SpeechPlayback } from "./speechPlayback";
import { FakeContext } from "./testing/fakeAudioContext";

const RATE = 24000;
const FORMAT = { sampleRate: RATE, channels: 1 };

function audio(seconds: number): Uint8Array {
  return new Uint8Array(Math.round(seconds * RATE) * 2);
}

function clock() {
  let at = 0;
  return {
    now: () => at,
    tick(ms: number) {
      at += ms;
    },
  };
}

function playback(context: FakeContext, time = clock()) {
  return { playback: new SpeechPlayback(context, FORMAT, { now: time.now }), time };
}

async function settle(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

describe("services/speechPlayback", () => {
  it("uma fala curta so comeca quando chega inteira, sem esperar um reservatorio que nao se forma", () => {
    const context = new FakeContext();
    const { playback: speech } = playback(context);
    const onStart = vi.fn();
    void speech.play(onStart);

    speech.push(audio(0.3));
    expect(onStart).not.toHaveBeenCalled();
    speech.finish(0.3 * RATE * 2);

    expect(onStart).toHaveBeenCalledTimes(1);
    expect(context.scheduledSeconds).toBeCloseTo(0.3, 3);
  });

  it("uma fala longa em rede boa comeca quando ja decidiu que o ritmo aguenta, sem esperar o fim", () => {
    const context = new FakeContext();
    const { playback: speech, time } = playback(context);
    const onStart = vi.fn();
    void speech.play(onStart);

    for (let piece = 0; piece < 4; piece += 1) {
      speech.push(audio(0.2));
      time.tick(20);
    }

    expect(onStart).toHaveBeenCalledTimes(1);
    expect(context.scheduledSeconds).toBeGreaterThanOrEqual(0.8 - 0.001);
  });

  it("nao comeca antes de ter o reservatorio e a decisao", () => {
    const context = new FakeContext();
    const { playback: speech, time } = playback(context);
    const onStart = vi.fn();
    void speech.play(onStart);

    speech.push(audio(0.3));
    time.tick(20);
    speech.push(audio(0.3));

    expect(onStart).not.toHaveBeenCalled();
    expect(context.sources).toHaveLength(0);
  });

  it("agenda cada pedaco no instante em que o anterior termina, sem folga nem sobreposicao", () => {
    const context = new FakeContext();
    const { playback: speech, time } = playback(context);
    void speech.play(() => undefined);
    for (let piece = 0; piece < 4; piece += 1) {
      speech.push(audio(0.2));
      time.tick(20);
    }

    for (let piece = 0; piece < 5; piece += 1) {
      speech.push(audio(0.1));
      time.tick(20);
    }

    const [first, ...rest] = context.sources;
    let expectedStart = first.endsAt;
    for (const source of rest) {
      expect(source.startedAt).toBeCloseTo(expectedStart, 6);
      expectedStart = source.endsAt;
    }
  });

  it("rede mais lenta que o audio espera a fala inteira e toca sem nenhum buraco", async () => {
    const context = new FakeContext();
    const { playback: speech, time } = playback(context);
    const onStart = vi.fn();
    const done = speech.play(onStart);

    for (let piece = 0; piece < 10; piece += 1) {
      speech.push(audio(0.1));
      time.tick(125);
    }

    expect(onStart).not.toHaveBeenCalled();
    expect(context.sources).toHaveLength(0);

    speech.finish(10 * 0.1 * RATE * 2);
    expect(onStart).toHaveBeenCalledTimes(1);
    context.advance(2);
    const outcome = await done;

    expect(outcome.underruns).toBe(0);
    expect(outcome.cut).toBe(false);
  });

  it("conta um esvaziamento quando o audio acaba antes de chegar o proximo pedaco", async () => {
    const context = new FakeContext();
    const { playback: speech, time } = playback(context);
    const done = speech.play(() => undefined);
    for (let piece = 0; piece < 4; piece += 1) {
      speech.push(audio(0.2));
      time.tick(20);
    }

    context.advance(2);
    speech.push(audio(0.2));
    speech.finish(5 * 0.2 * RATE * 2);
    context.advance(2);
    const outcome = await done;

    expect(outcome.underruns).toBe(1);
  });

  it("pedacos de tamanho impar nao perdem audio e o fim e conferido pelos bytes recebidos", async () => {
    const context = new FakeContext();
    const { playback: speech, time } = playback(context);
    const done = speech.play(() => undefined);
    const total = audio(1.0);

    let position = 0;
    for (const size of [701, 1203, 999, 2001]) {
      speech.push(total.slice(position, position + size));
      position += size;
      time.tick(5);
    }
    while (position < total.length) {
      speech.push(total.slice(position, position + 1501));
      position += 1501;
      time.tick(5);
    }
    speech.finish(total.length);
    context.advance(3);
    const outcome = await done;

    expect(context.scheduledSeconds).toBeCloseTo(1.0, 3);
    expect(outcome.receivedBytes).toBe(total.length);
    expect(outcome.cut).toBe(false);
  });

  it("uma fala que chega menor que o fim declarado e registrada como cortada", async () => {
    const context = new FakeContext();
    const { playback: speech } = playback(context);
    const done = speech.play(() => undefined);

    speech.push(audio(0.5));
    speech.finish(audio(1.0).length);
    context.advance(2);
    const outcome = await done;

    expect(outcome.cut).toBe(true);
    expect(outcome.expectedBytes).toBe(audio(1.0).length);
    expect(outcome.receivedBytes).toBe(audio(0.5).length);
  });

  it("a conexao que cai no meio da fala termina o que ja estava agendado e marca como cortada", async () => {
    const context = new FakeContext();
    const { playback: speech, time } = playback(context);
    const done = speech.play(() => undefined);
    for (let piece = 0; piece < 4; piece += 1) {
      speech.push(audio(0.2));
      time.tick(20);
    }

    speech.abort();
    context.advance(3);
    const outcome = await done;

    expect(outcome.cut).toBe(true);
    expect(outcome.expectedBytes).toBeNull();
  });

  it("so conta como tocada quando o ultimo som termina, e nao quando e agendado", async () => {
    const context = new FakeContext();
    const { playback: speech } = playback(context);
    let finished = false;
    void speech.play(() => undefined).then(() => {
      finished = true;
    });

    speech.push(audio(0.5));
    speech.finish(audio(0.5).length);
    await settle();

    expect(finished).toBe(false);
    context.advance(0.3);
    await settle();
    expect(finished).toBe(false);
    context.advance(1);
    await settle();
    expect(finished).toBe(true);
  });

  it("uma fala que ja chegou inteira enquanto a anterior tocava espera a vez e depois toca", () => {
    const context = new FakeContext();
    const { playback: speech } = playback(context);

    speech.push(audio(0.6));
    speech.finish(audio(0.6).length);
    expect(context.sources).toHaveLength(0);

    void speech.play(() => undefined);

    expect(context.scheduledSeconds).toBeCloseTo(0.6, 3);
  });

  it("recusa audio que nao seja mono", () => {
    const context = new FakeContext();

    expect(
      () => new SpeechPlayback(context, { sampleRate: RATE, channels: 2 }),
    ).toThrowError(/mono/);
  });

  it("uma fala sem nenhum audio, que o servidor declara vazia, termina na hora", async () => {
    const context = new FakeContext();
    const { playback: speech } = playback(context);
    const done = speech.play(() => undefined);

    speech.finish(0);
    const outcome = await done;

    expect(context.sources).toHaveLength(0);
    expect(outcome.receivedBytes).toBe(0);
    expect(outcome.cut).toBe(false);
  });
});

describe("services/speechPlayback, parando a fala", () => {
  it("parar interrompe o que estava agendado, termina a fala como cortada e nao deixa comecar mais nada", async () => {
    const context = new FakeContext();
    const { playback: speech, time } = playback(context);
    const done = speech.play(() => undefined);
    for (let piece = 0; piece < 4; piece += 1) {
      speech.push(audio(0.2));
      time.tick(20);
    }
    const scheduled = context.sources.length;

    speech.stop();
    speech.push(audio(0.2));
    const outcome = await done;

    expect(context.sources.every((source) => source.stopped)).toBe(true);
    expect(context.sources).toHaveLength(scheduled);
    expect(outcome.cut).toBe(true);
  });
});
