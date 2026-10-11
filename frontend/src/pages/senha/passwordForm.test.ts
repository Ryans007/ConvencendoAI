import { describe, expect, it } from "vitest";

import { validatePasswordForm } from "./passwordForm";

describe("validatePasswordForm", () => {
  it("aceita senha nova confirmada e diferente da temporaria", () => {
    expect(validatePasswordForm("Temp1234", "Nova#Senha1", "Nova#Senha1")).toBeNull();
  });

  it("pede os tres campos", () => {
    expect(validatePasswordForm("", "Nova#Senha1", "Nova#Senha1")).toMatch(/tres campos/);
    expect(validatePasswordForm("Temp1234", "", "")).toMatch(/tres campos/);
  });

  it("avisa quando a confirmacao e diferente da senha nova", () => {
    expect(validatePasswordForm("Temp1234", "Nova#Senha1", "Outra#Senha2")).toMatch(
      /confirmacao/,
    );
  });

  it("avisa quando a senha nova e igual a temporaria", () => {
    expect(validatePasswordForm("Temp1234", "Temp1234", "Temp1234")).toMatch(/igual/);
  });
});
