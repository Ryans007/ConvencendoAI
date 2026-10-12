/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** URL base da API, incluindo o prefixo. Definida no .env da raiz do repositorio. */
  readonly VITE_API_BASE_URL?: string;
  /** URL base da sessão de voz, incluindo o prefixo. Sem ela, usa /ws no host da página. */
  readonly VITE_WS_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
