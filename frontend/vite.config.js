import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Dev only: forward API calls to the FastAPI backend (port 8000). For a
  // deployed backend, set VITE_API_URL instead (see api/fetchItinerary.ts).
  server: {
    proxy: {
      '/itineraries': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
