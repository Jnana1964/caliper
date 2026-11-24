import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const PROXY = {
  target: process.env.VITE_API_TARGET || 'http://localhost:8000',
  changeOrigin: true,
  rewrite: (p) => p.replace(/^\/api/, ''),
}

export default defineConfig({
  plugins: [react()],
  // The API runs on 8000. Proxying keeps the browser on one origin,
  // so SSE works without CORS preflight weirdness.
  server: { port: 5173, proxy: { '/api': PROXY } },
  preview: { port: 4173, proxy: { '/api': PROXY } },
})
