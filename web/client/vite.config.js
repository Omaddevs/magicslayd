import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  // Telegram ichidagi eski brauzerlar (iOS 14+, Android WebView 87+) ham ochishi uchun
  build: { target: ['es2020', 'safari14', 'chrome87'] },
  server: {
    port: 5173,
    host: true,
    // Tunnel (ngrok / cloudflared) orqali Telegram'da ochish uchun
    allowedHosts: true,
    proxy: { '/api': 'http://localhost:3001' },
  },
});
