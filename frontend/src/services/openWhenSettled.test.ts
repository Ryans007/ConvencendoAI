import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { openWhenSettled } from "./openWhenSettled";

class FakeSession {
  static created = 0;
  disposed = false;

  constructor() {
    FakeSession.created += 1;
  }

  dispose(): void {
    this.disposed = true;
  }
}

beforeEach(() => {
  FakeSession.created = 0;
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("services/openWhenSettled", () => {
  it("nao cria a sessao no mesmo ciclo em que o efeito monta", () => {
    openWhenSettled(() => new FakeSession(), () => () => undefined);

    expect(FakeSession.created).toBe(0);
  });

  it("cria a sessao no ciclo seguinte e entrega ela a quem a liga", () => {
    const onOpen = vi.fn(() => () => undefined);

    openWhenSettled(() => new FakeSession(), onOpen);
    vi.runAllTimers();

    expect(FakeSession.created).toBe(1);
    expect(onOpen).toHaveBeenCalledWith(expect.any(FakeSession));
  });

  it("desmontar no mesmo ciclo desfaz antes de criar: o React em desenvolvimento nao abre conexao descartavel", () => {
    const first = openWhenSettled(() => new FakeSession(), () => () => undefined);
    first();
    openWhenSettled(() => new FakeSession(), () => () => undefined);
    vi.runAllTimers();

    expect(FakeSession.created).toBe(1);
  });

  it("desmontar depois de criada libera o que foi ligado e encerra a sessao", () => {
    const release = vi.fn();
    let created: FakeSession | null = null;
    const cleanup = openWhenSettled(
      () => (created = new FakeSession()),
      () => release,
    );
    vi.runAllTimers();

    cleanup();

    expect(release).toHaveBeenCalledTimes(1);
    expect(created!.disposed).toBe(true);
  });
});
