import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { fetchAttemptReport, type AttemptReport } from "../api/attemptReport";

/** Hook que expoe o relatorio de uma tentativa concluida a camada visual. */
export function useAttemptReport(attemptId: number): UseQueryResult<AttemptReport> {
  return useQuery({
    queryKey: ["attempt-report", attemptId],
    queryFn: ({ signal }) => fetchAttemptReport(attemptId, signal),
    retry: false,
  });
}
