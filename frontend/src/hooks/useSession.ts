import { useSyncExternalStore } from "react";

import { isAuthenticated, login, logout, register, subscribe } from "../services/session";

export interface UseSessionResult {
  authenticated: boolean;
  login: typeof login;
  register: typeof register;
  logout: typeof logout;
}

/** Hook que expoe o estado de autenticacao e as acoes de sessao aos componentes. */
export function useSession(): UseSessionResult {
  const authenticated = useSyncExternalStore(subscribe, isAuthenticated, isAuthenticated);
  return { authenticated, login, register, logout };
}
