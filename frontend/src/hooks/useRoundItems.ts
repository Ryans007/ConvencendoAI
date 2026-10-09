import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { fetchRound, type RoundPage } from "../api/reviewRound";

/**
 * Carrega a rodada: a primeira página dos itens vencidos do aluno.
 *
 * Não guarda cache nem refaz a busca ao voltar para a aba: uma rodada é um retrato do que
 * estava vencido ao começar, e trocá-la no meio da tela mudaria o item que o aluno está
 * respondendo. "Mais uma rodada" pede a busca de novo com `refetch`.
 */
export function useRoundItems(): UseQueryResult<RoundPage> {
  return useQuery({
    queryKey: ["review-round"],
    queryFn: ({ signal }) => fetchRound(signal),
    gcTime: 0,
    staleTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}
