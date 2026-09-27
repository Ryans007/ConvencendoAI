import { get } from "./client";

/** Estado reportado por um componente da infraestrutura. */
export type ComponentState = "ok" | "unreachable";

/** Resposta de `GET /api/health/`. */
export interface HealthStatus {
  application: ComponentState;
  database: ComponentState;
}

/** Consulta o estado da aplicacao e do banco. */
export function fetchHealth(signal?: AbortSignal): Promise<HealthStatus> {
  return get<HealthStatus>("/health/", { signal });
}
