import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { useSession } from "../hooks/useSession";

interface LogoutLinkProps {
  className?: string;
}

/**
 * Acao de encerrar a conta, discreta, presente em toda tela do fluxo do aluno. Ao sair
 * limpa as consultas guardadas, para o proximo aluno do mesmo navegador nao ver, nem por
 * um instante, o nome e os dados do anterior.
 */
export function LogoutLink({ className }: LogoutLinkProps) {
  const navigate = useNavigate();
  const { logout } = useSession();
  const queryClient = useQueryClient();

  async function handleClick() {
    await logout();
    queryClient.clear();
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
