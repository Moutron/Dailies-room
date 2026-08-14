import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // The FastAPI backend (`ui/server/`) runs separately in dev, on 8001.
      // Proxying keeps requests same-origin so no CORS setup is needed.
      '/chat': 'http://localhost:8001',
      // Only the API leaves under /clip/{id}/..., never the bare
      // /clip/{id} page route (Screen 5) -- a plain '/clip' prefix here
      // would swallow that route's own dev-server navigation/refresh and
      // return the backend's 404 instead of the SPA. Keys starting with
      // '^' are matched as RegExp (Vite proxy option).
      '^/clip/[^/]+/(url|meta|dialogue|thumbnails|circle)$': 'http://localhost:8001',
      '/thumbs': 'http://localhost:8001',
      '/posters': 'http://localhost:8001',
      '/stats': 'http://localhost:8001',
      '/coverage/matrix': 'http://localhost:8001',
      '/ingest/summary': 'http://localhost:8001',
      '/clips': 'http://localhost:8001',
      '/search': 'http://localhost:8001',
      // Only the API leaves under /shot-list/rows/..., never the bare
      // /shot-list page route (Screen 7) -- same '^'-anchored-regex
      // reasoning as the /clip/{id}/... leaf above (see Prompt 4's notes).
      '^/shot-list/rows(/.*)?$': 'http://localhost:8001',
      '/health': 'http://localhost:8001',
    },
  },
})
