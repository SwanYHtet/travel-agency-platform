import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    allowedHosts: ['agenta.local', 'agentb.local'],
    proxy: {
      // /api/phase2 must be listed BEFORE /api — Vite matches the first prefix
      // that fits, so the more-specific rule must come first.
      // Rewrite strips the /phase2 segment so port 8001 sees clean /api/... paths.
      '/api/phase2': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/phase2/, '/api'),
      },
      // Professor's backend on port 8000 handles auth, bookings, and RapidAPI search.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
