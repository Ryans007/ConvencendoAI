import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockPost = vi.fn();

vi.mock("../api/client", () => ({
  post: (...args: unknown[]) => mockPost(...args),
}));

function createMemoryStorage(): Storage {
  const store = new Map<string, string>();
  return {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => store.clear(),
    key: () => null,
    get length() {
      return store.size;
    },
  } as Storage;
}

describe("services/session", () => {
  beforeEach(() => {
    vi.resetModules();
    mockPost.mockReset();
    vi.stubGlobal("localStorage", createMemoryStorage());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renova o token de acesso usando o token de renovacao guardado", async () => {
    mockPost.mockResolvedValueOnce({ access: "access-1", refresh: "refresh-1" });
    const session = await import("./session");
    await session.login("aluno", "senha");
    expect(session.getAccessToken()).toBe("access-1");

    mockPost.mockResolvedValueOnce({ access: "access-2", refresh: "refresh-2" });
    const renewed = await session.refresh();
    expect(renewed).toBe(true);
    expect(session.getAccessToken()).toBe("access-2");
  });

  it("descarta a sessao quando o token de renovacao nao e mais valido", async () => {
    mockPost.mockResolvedValueOnce({ access: "access-1", refresh: "refresh-1" });
    const session = await import("./session");
    await session.login("aluno", "senha");

    mockPost.mockRejectedValueOnce(new Error("token invalido"));
    const renewed = await session.refresh();
    expect(renewed).toBe(false);
    expect(session.getAccessToken()).toBeNull();
    expect(session.isAuthenticated()).toBe(false);
  });

  it("logout bloqueia o token de renovacao e descarta a sessao mesmo se a chamada falhar", async () => {
    mockPost.mockResolvedValueOnce({ access: "access-1", refresh: "refresh-1" });
    const session = await import("./session");
    await session.login("aluno", "senha");

    mockPost.mockRejectedValueOnce(new Error("rede fora do ar"));
    await session.logout();
    expect(session.getAccessToken()).toBeNull();
    expect(session.isAuthenticated()).toBe(false);
  });

  it("bootstrap restaura a sessao a partir do token de renovacao persistido", async () => {
    const storage = createMemoryStorage();
    storage.setItem("convencendoai.refreshToken", "refresh-persisted");
    vi.stubGlobal("localStorage", storage);

    mockPost.mockResolvedValueOnce({ access: "access-3", refresh: "refresh-3" });
    const session = await import("./session");
    await session.bootstrap();

    expect(session.getAccessToken()).toBe("access-3");
    expect(mockPost).toHaveBeenCalledWith(
      "/auth/token/refresh/",
      { refresh: "refresh-persisted" },
      { skipAuth: true },
    );
  });
});
