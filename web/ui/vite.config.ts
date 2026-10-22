/// <reference types="vitest/config" />
import path from 'node:path'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Build sai direto para o pacote Python (src/roboto/web/static), de onde o Starlette serve o SPA.
// base '/': o index.html referencia /assets/... que o console monta via StaticFiles.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  build: {
    outDir: path.resolve(import.meta.dirname, '../../src/roboto/web/static'),
    emptyOutDir: true,
  },
  test: { environment: 'jsdom', globals: true, setupFiles: './src/setupTests.ts' },
})
