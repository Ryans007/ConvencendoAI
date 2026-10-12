import { describe, expect, it } from "vitest";
import { resolveApiBaseUrl, resolveWsBaseUrl } from "./origin";

describe("resolveApiBaseUrl", () => {
  it("usa /api na própria origem quando o build não configura a URL", () => {
    expect(resolveApiBaseUrl(undefined)).toBe("/api");
    expect(resolveApiBaseUrl("")).toBe("/api");
  });

  it("mantém a URL configurada, como no desenvolvimento", () => {
    expect(resolveApiBaseUrl("http://localhost:8010/api")).toBe("http://localhost:8010/api");
  });
});

describe("resolveWsBaseUrl", () => {
  it("usa wss no mesmo host quando a página veio por HTTPS", () => {
    const location = { protocol: "https:", host: "app.exemplo.com.br" };
    expect(resolveWsBaseUrl(undefined, location)).toBe("wss://app.exemplo.com.br/ws");
  });

  it("usa ws no mesmo host quando a página veio por HTTP, mantendo a porta", () => {
    const location = { protocol: "http:", host: "localhost:8080" };
    expect(resolveWsBaseUrl(undefined, location)).toBe("ws://localhost:8080/ws");
  });

  it("mantém a URL configurada, como no desenvolvimento", () => {
    const location = { protocol: "http:", host: "localhost:5180" };
    expect(resolveWsBaseUrl("ws://localhost:8010/ws", location)).toBe("ws://localhost:8010/ws");
  });
});
