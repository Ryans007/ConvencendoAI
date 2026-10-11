import { useSyncExternalStore } from "react";

import {
  changePassword,
  isAuthenticated,
  isPasswordChangeRequired,
  login,
  logout,
  subscribe,
} from "../services/session";

export interface UseSessionResult {
  authenticated: boolean;
  passwordChangeRequired: boolean;
  login: typeof login;
  changePassword: typeof changePassword;
  logout: typeof logout;
}

/** Hook que expoe o estado de autenticacao e as acoes de sessao aos componentes. */
export function useSession(): UseSessionResult {
  const authenticated = useSyncExternalStore(subscribe, isAuthenticated, isAuthenticated);
  const passwordChangeRequired = useSyncExternalStore(
    subscribe,
    isPasswordChangeRequired,
    isPasswordChangeRequired,
  );
  return { authenticated, passwordChangeRequired, login, changePassword, logout };
}
