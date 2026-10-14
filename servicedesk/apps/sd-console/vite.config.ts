import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

declare const process: { env: Record<string, string | undefined> };

// Servido em /sd-console/ no mesmo site do Chatwoot (CTI_AUTH.md §2: cookie primário).
// Em dev, o proxy encaminha /sd-ops e /sd-qa para os serviços locais.
export default defineConfig({
  base: '/sd-console/',
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5180,
    proxy: {
      '/sd-ops': process.env.SDOPS_PROXY || 'http://127.0.0.1:8081',
      '/sd-qa': process.env.SDQA_PROXY || 'http://127.0.0.1:8090',
    },
  },
  build: { sourcemap: false, chunkSizeWarningLimit: 400 },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['src/test/setup.ts'],
    css: false,
  },
});
