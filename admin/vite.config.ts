import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ command }) => ({
  plugins: [react(), tailwindcss()],
  envDir: command === 'serve' ? '../frontend' : '.',
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: { port: 5176, host: 'localhost', strictPort: true },
}));
