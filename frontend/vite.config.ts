import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Durante el desarrollo (`npm run dev`) las llamadas a /api se reenvían al
// backend en el puerto 8000. En producción nginx hace ese mismo trabajo.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
