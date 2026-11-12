import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    target: 'es2020',
    // three.js lives in a lazily-loaded chunk shared by the hero scene and the CTA sea
    chunkSizeWarningLimit: 1000,
  },
});
