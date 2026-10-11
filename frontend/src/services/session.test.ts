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

  it("login com a senha temporaria marca a troca de senha como obrigatoria", async () => {
    mockPost.mockResolvedValueOnce({
      access: "access-1",
      refresh: "refresh-1",
      must_change_password: true,
    });
    const session = await import("./session");

    await session.login("maria", "temporaria");

    expect(session.isPasswordChangeRequired()).toBe(true);
    expect(session.isAuthenticated()).toBe(true);
  });

  it("login de quem ja definiu a senha nao marca a troca", async () => {
    mockPost.mockResolvedValueOnce({
      access: "access-1",
      refresh: "refresh-1",
      must_change_password: false,
    });
    const session = await import("./session");

    await session.login("aluno", "senha");

    expect(session.isPasswordChangeRequired()).toBe(false);
  });

  it("a renovacao do token nao desfaz a troca pendente", async () => {
    mockPost.mockResolvedValueOnce({
      access: "access-1",
      refresh: "refresh-1",
      must_change_password: true,
    });
    const session = await import("./session");
    await session.login("maria", "temporaria");

    mockPost.mockResolvedValueOnce({ access: "access-2", refresh: "refresh-2" });
    await session.refresh();

    expect(session.isPasswordChangeRequired()).toBe(true);
  });

  it("requirePasswordChange avisa os assinantes uma unica vez", async () => {
    const session = await import("./session");
    const listener = vi.fn();
    session.subscribe(listener);

    session.requirePasswordChange();
    session.requirePasswordChange();

    expect(session.isPasswordChangeRequired()).toBe(true);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("trocar a senha envia a atual e a nova, guarda os tokens novos e libera o app", async () => {
    mockPost.mockResolvedValueOnce({
      access: "access-1",
      refresh: "refresh-1",
      must_change_password: true,
    });
    const session = await import("./session");
    await session.login("maria", "temporaria");

    mockPost.mockResolvedValueOnce({ access: "access-2", refresh: "refresh-2" });
    await session.changePassword("temporaria", "Nova#Senha1");

    expect(mockPost).toHaveBeenLastCalledWith("/auth/password/", {
      current_password: "temporaria",
      new_password: "Nova#Senha1",
    });
    expect(session.getAccessToken()).toBe("access-2");
    expect(session.isPasswordChangeRequired()).toBe(false);
  });

  it("uma troca recusada pela API mantem a pendencia e os tokens atuais", async () => {
    mockPost.mockResolvedValueOnce({
      access: "access-1",
      refresh: "refresh-1",
      must_change_password: true,
    });
    const session = await import("./session");
    await session.login("maria", "temporaria");

    mockPost.mockRejectedValueOnce(new Error("senha fraca"));
    await expect(session.changePassword("temporaria", "123")).rejects.toThrow();

    expect(session.getAccessToken()).toBe("access-1");
    expect(session.isPasswordChangeRequired()).toBe(true);
  });

  it("sair descarta tambem a pendencia de troca", async () => {
    mockPost.mockResolvedValueOnce({
      access: "access-1",
      refresh: "refresh-1",
      must_change_password: true,
    });
    const session = await import("./session");
    await session.login("maria", "temporaria");

    mockPost.mockResolvedValueOnce(undefined);
    await session.logout();

    expect(session.isPasswordChangeRequired()).toBe(false);
  });
});
