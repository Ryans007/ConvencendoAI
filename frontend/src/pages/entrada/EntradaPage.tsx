import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { Logo } from "../../components/Logo";
import { useSession } from "../../hooks/useSession";
import { authErrorMessage } from "./errorMessage";

type Mode = "login" | "register";

const FOOTER: Record<Mode, string> = {
  login: "Sem conta? Criar leva menos de um minuto.",
  register: "Ao criar a conta voce ja entra direto na sua jornada.",
};

/** Tela de entrada: login e registro, unico ponto de acesso publico do app. */
export default function EntradaPage() {
  const { authenticated, login, register } = useSession();
  const navigate = useNavigate();
  const location = useLocation();

  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (authenticated) {
    const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname;
    return <Navigate to={from ?? "/jornada"} replace />;
  }

  function changeMode(next: Mode) {
    setMode(next);
    setError(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedUsername = username.trim();
    if (!trimmedUsername || !password || busy) {
      return;
    }

    setBusy(true);
    setError(null);
    try {
      if (mode === "register") {
        await register(trimmedUsername, password);
      } else {
        await login(trimmedUsername, password);
      }
      navigate("/jornada", { replace: true });
    } catch (cause) {
      setError(authErrorMessage(cause));
      setBusy(false);
    }
  }

  const ready = username.trim().length > 0 && password.length > 0;
  const blocked = !ready || busy;

  return (
    <div className="flex min-h-screen items-center justify-center bg-app px-8 py-12">
      <div className="flex w-full max-w-[400px] flex-col items-center gap-7">
        <div className="flex items-center gap-2.5">
          <Logo size={28} />
          <span className="text-page-title font-semibold tracking-tight">ConvencendoAI</span>
        </div>

        <div className="w-full rounded-card border border-line bg-surface p-7 shadow-card-focus">
          <div className="flex gap-1 rounded-pill bg-app p-1">
            <button
              type="button"
              onClick={() => changeMode("login")}
              className={`flex-1 rounded-pill px-3 py-2 text-scenario font-medium ${
                mode === "login" ? "bg-surface text-ink shadow-card" : "text-ink-muted"
              }`}
            >
              Entrar
            </button>
            <button
              type="button"
              onClick={() => changeMode("register")}
              className={`flex-1 rounded-pill px-3 py-2 text-scenario font-medium ${
                mode === "register" ? "bg-surface text-ink shadow-card" : "text-ink-muted"
              }`}
            >
              Criar conta
            </button>
          </div>

          <form onSubmit={handleSubmit} className="mt-5 flex flex-col gap-4">
            <label className="flex flex-col gap-1.5">
              <span className="text-aux font-medium text-ink-muted">Usuario</span>
              <input
                type="text"
                autoComplete="username"
                placeholder="seu.usuario"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                className="rounded-[10px] border border-line px-3 py-2.5 text-scenario outline-none focus:border-brand"
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-aux font-medium text-ink-muted">Senha</span>
              <input
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                placeholder="********"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="rounded-[10px] border border-line px-3 py-2.5 text-scenario outline-none focus:border-brand"
              />
            </label>

            {error !== null && (
              <div className="flex items-start gap-2 rounded-[10px] border border-warn-soft bg-warn-soft px-3 py-2.5">
                <span className="text-aux text-warn-strong">{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={blocked}
              className={`mt-0.5 w-full rounded-pill px-5 py-3.5 text-scenario font-semibold text-white ${
                blocked ? "cursor-default bg-brand-line-strong" : "cursor-pointer bg-brand"
              }`}
            >
              {busy
                ? mode === "login"
                  ? "Entrando..."
                  : "Criando conta..."
                : mode === "login"
                  ? "Entrar"
                  : "Criar conta"}
            </button>
          </form>
        </div>

        <span className="text-center text-aux text-ink-muted">{FOOTER[mode]}</span>
      </div>
    </div>
  );
}
