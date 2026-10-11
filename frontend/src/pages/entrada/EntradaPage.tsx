import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { Logo } from "../../components/Logo";
import { useSession } from "../../hooks/useSession";
import { isPasswordChangeRequired } from "../../services/session";
import { authErrorMessage } from "./errorMessage";

/** Tela de entrada: so login, unico ponto de acesso publico do app. O acesso e criado pelo administrador. */
export default function EntradaPage() {
  const { authenticated, passwordChangeRequired, login } = useSession();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (authenticated) {
    if (passwordChangeRequired) {
      return <Navigate to="/definir-senha" replace />;
    }
    const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname;
    return <Navigate to={from ?? "/jornada"} replace />;
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
      await login(trimmedUsername, password);
      navigate(isPasswordChangeRequired() ? "/definir-senha" : "/jornada", { replace: true });
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
          <h1 className="text-scenario font-semibold">Entrar</h1>

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
                autoComplete="current-password"
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
              {busy ? "Entrando..." : "Entrar"}
            </button>
          </form>
        </div>

        <span className="text-center text-aux text-ink-muted">
          O acesso e liberado pelo administrador. Sem acesso, fale com ele.
        </span>
      </div>
    </div>
  );
}
