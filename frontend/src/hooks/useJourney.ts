import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { fetchJourney, type TrackState } from "../api/journey";

/** Hook que expoe a jornada do aluno autenticado a camada visual. */
export function useJourney(): UseQueryResult<TrackState[]> {
  return useQuery({
    queryKey: ["journey"],
    queryFn: ({ signal }) => fetchJourney(signal),
  });
}
