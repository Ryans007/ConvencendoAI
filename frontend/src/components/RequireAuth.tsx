import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useSession } from "../hooks/useSession";

/**
 * Guarda de rota: sem sessao valida, redireciona para a Entrada; com a troca da senha
 * temporaria pendente, leva a tela de definir a senha. Nos dois casos sem carregar a tela
 * pedida.
 */
export function RequireAuth() {
  const { authenticated, passwordChangeRequired } = useSession();
  const location = useLocation();

  if (!authenticated) {
    return <Navigate to="/entrada" replace state={{ from: location }} />;
  }
  if (passwordChangeRequired) {
    return <Navigate to="/definir-senha" replace />;
  }
  return <Outlet />;
}
