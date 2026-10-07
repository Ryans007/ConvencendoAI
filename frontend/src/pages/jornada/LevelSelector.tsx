import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import type { LevelState } from "../../api/journey";
import { levelDash, type LevelDash } from "./journeyView";

interface LevelSelectorProps {
  scenarioSlug: string;
  levels: LevelState[];
  selectedOrder: number;
  onSelect: (order: number) => void;
}

const DASH_COLOR: Record<LevelDash, string> = {
  approved: "bg-brand",
  attempted: "bg-warn",
  untried: "bg-line",
};

const DASH_WORD: Record<LevelDash, string> = {
  approved: "aprovado",
  attempted: "tentado, ainda não aprovado",
  untried: "nunca tentado",
};

/**
 * Os tracinhos de nível de um cenário, como um grupo de opções.
 *
 * Passar o mouse seleciona o nível, e a seleção continua depois que o mouse sai, para o
 * aluno chegar à ação do cartão sem perder o que escolheu. Clicar ou tocar seleciona e abre a
 * descrição do nível. O toque não seleciona ao encostar, só ao tocar, para não disparar duas
 * vezes. Só o nível selecionado entra na ordem do Tab, e as setas mudam a seleção.
 */
export function LevelSelector({ scenarioSlug, levels, selectedOrder, onSelect }: LevelSelectorProps) {
  const [describing, setDescribing] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const radioRefs = useRef<Record<number, HTMLButtonElement | null>>({});
  const descriptionId = `level-description-${scenarioSlug}`;
  const selected = levels.find((level) => level.order === selectedOrder);

  useEffect(() => {
    if (!describing) {
      return;
    }
    function closeOnOutsidePointer(event: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setDescribing(false);
      }
    }
    function closeOnEscape(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        setDescribing(false);
      }
    }
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [describing]);

  function choose(order: number, withDescription: boolean) {
    onSelect(order);
    setDescribing(withDescription);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const step = ["ArrowRight", "ArrowDown"].includes(event.key)
      ? 1
      : ["ArrowLeft", "ArrowUp"].includes(event.key)
        ? -1
        : 0;
    if (step === 0) {
      return;
    }
    event.preventDefault();
    const next = levels[(index + step + levels.length) % levels.length];
    choose(next.order, false);
    radioRefs.current[next.order]?.focus();
  }

  return (
    <div ref={rootRef} className="flex flex-col gap-1">
      <div role="radiogroup" aria-label="Nível" className="flex w-full max-w-[200px] gap-1.5">
        {levels.map((level, index) => {
          const isSelected = level.order === selectedOrder;
          const dash = levelDash(level);
          return (
            <button
              key={level.order}
              ref={(element) => {
                radioRefs.current[level.order] = element;
              }}
              type="button"
              role="radio"
              aria-checked={isSelected}
              aria-label={`Nível ${level.order}, ${level.name}, ${DASH_WORD[dash]}`}
              aria-controls={isSelected && describing ? descriptionId : undefined}
              tabIndex={isSelected ? 0 : -1}
              onPointerEnter={(event) => {
                if (event.pointerType === "mouse" && !isSelected) {
                  choose(level.order, false);
                }
              }}
              onClick={() => choose(level.order, isSelected ? !describing : true)}
              onKeyDown={(event) => handleKeyDown(event, index)}
              className="group flex h-11 flex-1 cursor-pointer items-center rounded-[6px] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand-strong"
            >
              <span
                className={`block w-full rounded-pill transition-[height] ${DASH_COLOR[dash]} ${
                  isSelected ? "h-2 ring-2 ring-brand-line-strong ring-offset-1" : "h-1.5 group-hover:h-2"
                }`}
              />
            </button>
          );
        })}
      </div>

      {selected && (
        <span className="text-aux text-ink-muted">
          Nível {selected.order} &middot; {selected.name}
        </span>
      )}

      {describing && selected && (
        <div
          id={descriptionId}
          role="group"
          aria-label={`Descrição do nível ${selected.order}`}
          className="mt-1 max-w-[320px] rounded-[12px] border border-line bg-surface p-3.5 shadow-card-focus"
        >
          <p className="text-score font-semibold">
            {selected.name}
            <span className="font-medium text-ink-muted"> &middot; {selected.expected_cefr}</span>
          </p>
          <p className="mt-1 text-aux leading-relaxed text-ink-muted">{selected.expected_production}</p>
        </div>
      )}
    </div>
  );
}
