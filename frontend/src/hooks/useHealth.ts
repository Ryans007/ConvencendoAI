/** Hook que expoe o estado de sanidade do backend para a camada visual. */

import { useEffect, useState } from "react";

import { fetchHealth, type HealthStatus } from "../api/health";

/** Resultado da consulta, nos tres estados possiveis. */
export interface UseHealthResult {
  status: HealthStatus | null;
  error: string | null;
  loading: boolean;
}

/**
 * Consulta o endpoint de sanidade uma vez, ao montar.
 *
 * A requisicao e abortada se o componente desmontar antes da resposta, para nao
 * atualizar estado de um componente que nao existe mais.
 */
export function useHealth(): UseHealthResult {
  const [status, setStatus] = useState<HealthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const controller = new AbortController();

    fetchHealth(controller.signal)
      .then((resultado) => {
        setStatus(resultado);
        setError(null);
      })
      .catch((causa: unknown) => {
        if (causa instanceof DOMException && causa.name === "AbortError") {
          return;
        }
        setError(causa instanceof Error ? causa.message : "Falha desconhecida.");
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });

    return () => controller.abort();
  }, []);

  return { status, error, loading };
}
