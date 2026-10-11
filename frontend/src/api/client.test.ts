import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockRequirePasswordChange = vi.fn();
const mockEndSession = vi.fn();
const mockRefresh = vi.fn();

vi.mock("../services/session", () => ({
  getAccessToken: () => "access-1",
  refresh: () => mockRefresh(),
  endSession: () => mockEndSession(),
  requirePasswordChange: () => mockRequirePasswordChange(),
}));

function respond(status: number, body: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      status,
      ok: status >= 200 && status < 300,
      json: () => Promise.resolve(body),
    }),
  );
}

describe("api/client", () => {
  beforeEach(() => {
    vi.resetModules();
    mockRequirePasswordChange.mockReset();
    mockEndSession.mockReset();
    mockRefresh.mockReset().mockResolvedValue(false);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("marca a troca de senha como obrigatoria ao receber o 403 com o codigo proprio", async () => {
    respond(403, { detail: "Defina uma senha nova antes de continuar.", code: "password_change_required" });
    const { get, ApiError } = await import("./client");

    await expect(get("/journey/")).rejects.toBeInstanceOf(ApiError);

    expect(mockRequirePasswordChange).toHaveBeenCalledTimes(1);
  });

  it("nao marca a troca em um 403 de outro motivo", async () => {
    respond(403, { detail: "Sem permissao." });
    const { get } = await import("./client");

    await expect(get("/journey/")).rejects.toThrow();

    expect(mockRequirePasswordChange).not.toHaveBeenCalled();
  });

  it("descarta a sessao quando a chamada repetida depois de renovar continua recusada", async () => {
    mockRefresh.mockResolvedValue(true);
    respond(401, { detail: "Token invalido." });
    const { get } = await import("./client");

    await expect(get("/journey/")).rejects.toThrow();

    expect(mockEndSession).toHaveBeenCalledTimes(1);
  });

  it("nao descarta a sessao quando a renovacao resolve a chamada", async () => {
    mockRefresh.mockResolvedValue(true);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ status: 401, ok: false, json: () => Promise.resolve({}) })
      .mockResolvedValueOnce({ status: 200, ok: true, json: () => Promise.resolve({ ok: 1 }) });
    vi.stubGlobal("fetch", fetchMock);
    const { get } = await import("./client");

    await expect(get("/journey/")).resolves.toEqual({ ok: 1 });

    expect(mockEndSession).not.toHaveBeenCalled();
  });
});
