import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  server: {
    proxy: { '/api': process.env.API ?? 'http://localhost:8000', '/ws': { target: (process.env.API ?? 'http://localhost:8000').replace('http', 'ws'), ws: true } },
  },
});
