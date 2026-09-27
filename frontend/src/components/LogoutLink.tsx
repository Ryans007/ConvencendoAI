import { useNavigate } from "react-router-dom";

import { useSession } from "../hooks/useSession";

interface LogoutLinkProps {
  className?: string;
}

/** Acao de encerrar a conta, discreta, presente em toda tela do fluxo do aluno. */
export function LogoutLink({ className }: LogoutLinkProps) {
  const navigate = useNavigate();
  const { logout } = useSession();

  async function handleClick() {
    await logout();
    navigate("/entrada", { replace: true });
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className={className ?? "text-aux text-ink-muted hover:text-ink"}
    >
      Sair da conta
    </button>
  );
}
