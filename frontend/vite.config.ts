import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxy all /api requests to the FastAPI backend during development so
    // the frontend and backend can run on different ports without CORS issues.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // Output directory consumed by the nginx stage in the Docker multi-stage build.
    outDir: 'dist',
    sourcemap: false,
  },
})
