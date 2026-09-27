import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useSession } from "../hooks/useSession";

/** Guarda de rota: sem sessao valida, redireciona para a Entrada sem carregar a tela pedida. */
export function RequireAuth() {
  const { authenticated } = useSession();
  const location = useLocation();

  if (!authenticated) {
    return <Navigate to="/entrada" replace state={{ from: location }} />;
  }
  return <Outlet />;
}
