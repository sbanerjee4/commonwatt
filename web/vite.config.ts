import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// Clean Vite config for the Commonwatt SPA. Intentionally does NOT carry over
// Figma Make's preview-harness plugins (site.json shell, error-overlay replay,
// make-kit stories route, linked-package sourcemaps) — those are specific to
// Figma's preview iframe and don't belong in the shipped app.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    // 5173 matches the BFF CORS allowlist in bff/app.py.
    host: '127.0.0.1',
    port: 5173,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
})
