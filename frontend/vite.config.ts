import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'swallow-inbound-socket-errors',
      configureServer(server) {
        server.httpServer?.on('connection', (socket) => {
          socket.on('error', () => {})
        })
      },
    },
  ],
  server: {
    host: true,
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        timeout: 600000,
        proxyTimeout: 600000,
      }
    }
  }
})
