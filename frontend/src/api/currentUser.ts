import { get } from "./client";

/** Quem esta autenticado. */
export interface CurrentUser {
  username: string;
}

/** Chamada e tipos de `GET /auth/me/`: o aluno autenticado. */
export function fetchCurrentUser(signal?: AbortSignal): Promise<CurrentUser> {
  return get<CurrentUser>("/auth/me/", { signal });
}
