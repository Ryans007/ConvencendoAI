import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { fetchReviewSummary, type ReviewSummary } from "../api/reviewSummary";

/**
 * Resumo da revisão do aluno, compartilhado pelo menu, pela barra da jornada e pela tela de
 * revisão. A chave única faz as três telas dividirem a mesma consulta, e o `staleTime` zero
 * a refaz ao voltar para a jornada, para o número refletir a sessão que acabou de terminar.
 */
export function useReviewSummary(): UseQueryResult<ReviewSummary> {
  return useQuery({
    queryKey: ["review-summary"],
    queryFn: ({ signal }) => fetchReviewSummary(signal),
  });
}
