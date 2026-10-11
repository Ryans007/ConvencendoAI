import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { fetchCurrentUser, type CurrentUser } from "../api/currentUser";

/** O aluno autenticado, para o menu lateral mostrar o nome de usuario. */
export function useCurrentUser(): UseQueryResult<CurrentUser> {
  return useQuery({
    queryKey: ["current-user"],
    queryFn: ({ signal }) => fetchCurrentUser(signal),
  });
}
