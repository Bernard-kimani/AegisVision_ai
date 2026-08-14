import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// base: './' so the built asset URLs are relative -- main.py loads
// frontend/dist/index.html via a file:// path when packaged, which breaks
// with Vite's default absolute '/assets/...' base.
export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
  },
})
