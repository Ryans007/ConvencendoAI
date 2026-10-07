import { useState } from "react";

import type { ScenarioState } from "../../api/journey";
import { LevelSelector } from "./LevelSelector";
import { LevelStatusColumn } from "./LevelStatusColumn";
import { castLine, initialLevelOrder } from "./journeyView";

interface ScenarioCardProps {
  trackTitle: string;
  scenario: ScenarioState;
}

/**
 * Cartão de um cenário: título, elenco, os tracinhos de nível e, à direita, o estado e a ação
 * do nível selecionado. Um cenário bloqueado mostra só o motivo, sem nível para escolher.
 */
export function ScenarioCard({ trackTitle, scenario }: ScenarioCardProps) {
  const [selectedOrder, setSelectedOrder] = useState(() => initialLevelOrder(scenario));
  const approvedCount = scenario.level_states.filter((level) => level.approved).length;
  const selected = scenario.level_states.find((level) => level.order === selectedOrder);
  const cast = castLine(scenario.cast);

  return (
    <article
      className={`rounded-card border border-line bg-surface p-5 shadow-card ${
        scenario.unlocked ? "" : "opacity-70"
      }`}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="flex flex-col gap-1">
            <h3 className={`text-scenario font-medium ${scenario.unlocked ? "text-ink" : "text-ink-disabled"}`}>
              {scenario.title}
            </h3>
            {cast && <p className="text-aux text-ink-muted">{cast}</p>}
          </div>

          {scenario.unlocked ? (
            <div className="flex flex-col gap-1">
              <LevelSelector
                scenarioSlug={scenario.slug}
                levels={scenario.level_states}
                selectedOrder={selectedOrder}
                onSelect={setSelectedOrder}
              />
              <span className="text-aux text-ink-muted">
                {approvedCount} de {scenario.level_states.length} níveis
              </span>
            </div>
          ) : (
            <p className="text-aux text-ink-muted">Conclua o cenário anterior para desbloquear.</p>
          )}
        </div>

        {scenario.unlocked && selected && (
          <LevelStatusColumn trackTitle={trackTitle} scenario={scenario} level={selected} />
        )}
      </div>
    </article>
  );
}
