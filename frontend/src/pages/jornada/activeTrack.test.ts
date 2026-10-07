import { describe, expect, it } from "vitest";

import type { TrackState } from "../../api/journey";
import { activeTrack } from "./activeTrack";

function track(slug: string, unlocked: boolean, completed: boolean): TrackState {
  return {
    slug,
    title: slug,
    order: 1,
    student_role: `papel de ${slug}`,
    unlocked,
    completed,
    approved_levels: 0,
    possible_levels: 0,
    performance: null,
    scenario_states: [],
  };
}

describe("activeTrack", () => {
  it("é a primeira liberada e não concluída", () => {
    const tracks = [track("a", true, true), track("b", true, false), track("c", false, false)];

    expect(activeTrack(tracks)?.slug).toBe("b");
  });

  it("é a primeira quando todas estão concluídas", () => {
    const tracks = [track("a", true, true), track("b", true, true)];

    expect(activeTrack(tracks)?.slug).toBe("a");
  });

  it("não existe antes de a jornada carregar", () => {
    expect(activeTrack(undefined)).toBeUndefined();
  });
});
