/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** URL base da API, incluindo o prefixo. Definida no .env da raiz do repositorio. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
