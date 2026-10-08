import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In Docker the nginx image proxies /api to the backend; during local
// `npm run dev` Vite proxies /api to the backend on localhost:8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
