import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    assetsInlineLimit: (file) => (/\.woff2?$/.test(file) ? false : undefined),
  },
  server: {
    // Escuta em todas as interfaces porque o dev server roda dentro do container e
    // precisa ser alcancavel pelo navegador, que roda no host.
    host: true,
    watch: {
      // O bind mount do Docker Desktop para Windows entrega o conteudo do arquivo, mas
      // nao propaga os eventos de inotify que o watcher do Vite espera: sem polling o
      // HMR simplesmente nunca dispara. Medido neste projeto. Curiosamente o watcher do
      // backend (watchfiles) recebe os eventos normalmente, entao o problema nao e do
      // mount em si, e sim de como cada watcher observa.
      usePolling: true,
      interval: 300,
    },
  },
})
