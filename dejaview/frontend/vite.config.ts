import { resolve } from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const host = process.env.TAURI_DEV_HOST

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    // Tauri uses ES modules
    target: 'esnext',
  },
  resolve: {
    alias: {
      '@help': resolve(__dirname, '../resources/help'),
    },
  },
  // Vite options tailored for Tauri development
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    host: host || false,
    hmr: host ? { protocol: 'ws', host, port: 1421 } : undefined,
    watch: {
      // tell vite to ignore watching `src-tauri`
      ignored: ['**/src-tauri/**'],
      // WSL2: inotify is unreliable on Windows-hosted filesystems; use polling
      usePolling: true,
      interval: 500,
    },
  },
})
