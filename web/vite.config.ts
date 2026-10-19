import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    fs: {
      allow: [
        fileURLToPath(new URL('.', import.meta.url)),
        fileURLToPath(new URL('../README.md', import.meta.url)),
      ],
    },
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: { environment: 'jsdom' },
})
