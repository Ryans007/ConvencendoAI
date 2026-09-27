import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { fetchScenarioBriefing, type ScenarioBriefing } from "../api/scenarioBriefing";

/** Hook que expoe o briefing de um cenario e nivel a camada visual. */
export function useScenarioBriefing(
  scenarioSlug: string,
  levelOrder: number,
): UseQueryResult<ScenarioBriefing> {
  return useQuery({
    queryKey: ["scenario-briefing", scenarioSlug, levelOrder],
    queryFn: ({ signal }) => fetchScenarioBriefing(scenarioSlug, levelOrder, signal),
  });
}
