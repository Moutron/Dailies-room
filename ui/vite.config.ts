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
      '/clip': 'http://localhost:8001',
      '/thumbs': 'http://localhost:8001',
      '/health': 'http://localhost:8001',
    },
  },
})
