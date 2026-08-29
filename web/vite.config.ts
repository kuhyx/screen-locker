import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The Python API (`screen-locker-web`) runs on 127.0.0.1:8770 — 8000 belongs to
// steam-backlog-enforcer's own UI. In dev, Vite serves the UI and proxies
// `/api/*` to it, so there are no CORS concerns. In production the Python
// server serves the built bundle from `web/dist`.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8770',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/test/**',
        'src/main.tsx',
        'src/vite-env.d.ts',
      ],
      thresholds: {
        statements: 100,
        branches: 100,
        functions: 100,
        lines: 100,
      },
    },
  },
})
