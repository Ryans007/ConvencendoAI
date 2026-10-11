import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { Logo } from "../../components/Logo";
import { LogoutLink } from "../../components/LogoutLink";
import { useSession } from "../../hooks/useSession";
import { authErrorMessage } from "../entrada/errorMessage";
import { validatePasswordForm } from "./passwordForm";

/**
 * Tela de definir a senha: o aluno que entrou com a senha temporaria so chega ate aqui, ou
 * a sair. Depois da troca a API devolve tokens novos e ele segue para a jornada.
 */
export default function DefinirSenhaPage() {
  const { authenticated, changePassword } = useSession();
  const navigate = useNavigate();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!authenticated) {
    return <Navigate to="/entrada" replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) {
      return;
    }
    const problem = validatePasswordForm(currentPassword, newPassword, confirmation);
    if (problem !== null) {
      setError(problem);
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await changePassword(currentPassword, newPassword);
      navigate("/jornada", { replace: true });
    } catch (cause) {
      setError(authErrorMessage(cause));
      setBusy(false);
    }
  }

  const inputClass =
    "rounded-[10px] border border-line px-3 py-2.5 text-scenario outline-none focus:border-brand";

  return (
    <div className="flex min-h-screen items-center justify-center bg-app px-8 py-12">
      <div className="flex w-full max-w-[400px] flex-col items-center gap-7">
        <div className="flex items-center gap-2.5">
          <Logo size={28} />
          <span className="text-page-title font-semibold tracking-tight">ConvencendoAI</span>
        </div>

        <div className="w-full rounded-card border border-line bg-surface p-7 shadow-card-focus">
          <h1 className="text-scenario font-semibold">Defina sua senha</h1>
          <p className="mt-1.5 text-aux text-ink-muted">
            Voce entrou com uma senha temporaria. Escolha uma senha so sua para continuar.
          </p>

          <form onSubmit={handleSubmit} className="mt-5 flex flex-col gap-4">
            <label className="flex flex-col gap-1.5">
              <span className="text-aux font-medium text-ink-muted">Senha temporaria</span>
              <input
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                className={inputClass}
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-aux font-medium text-ink-muted">Senha nova</span>
              <input
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                className={inputClass}
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-aux font-medium text-ink-muted">Confirme a senha nova</span>
              <input
                type="password"
                autoComplete="new-password"
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                className={inputClass}
              />
            </label>

            {error !== null && (
              <div
                role="alert"
                className="flex items-start gap-2 rounded-[10px] border border-warn-soft bg-warn-soft px-3 py-2.5"
              >
                <span className="text-aux text-warn-strong">{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={busy}
              className={`mt-0.5 w-full rounded-pill px-5 py-3.5 text-scenario font-semibold text-white ${
                busy ? "cursor-default bg-brand-line-strong" : "cursor-pointer bg-brand"
              }`}
            >
              {busy ? "Salvando..." : "Definir senha"}
            </button>
          </form>
        </div>

        <LogoutLink />
      </div>
    </div>
  );
}
