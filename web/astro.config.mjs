import { defineConfig } from 'astro/config'

// The Python API (`screen-locker-web`) runs on 127.0.0.1:8770 — 8000 belongs to
// steam-backlog-enforcer's own UI. In dev, Astro serves the UI and proxies
// `/api/*` to it, so there are no CORS concerns. In production the Python
// server serves the built bundle from `web/dist`.
export default defineConfig({
  output: 'static',
  vite: {
    server: {
      proxy: {
        '/api': 'http://127.0.0.1:8770',
      },
    },
  },
})
