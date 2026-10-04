import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  root: 'frontend',
  base: '/',
  plugins: [vue(), tailwindcss()],
  server: {
    proxy: {
      '/api': process.env.OPPLE_API_TARGET || 'http://127.0.0.1:8080',
      '/auth': process.env.OPPLE_API_TARGET || 'http://127.0.0.1:8080',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
