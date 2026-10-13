// Test-only Clerk substitution. Production configuration never imports this file.
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath, URL } from 'node:url';
export default defineConfig({cacheDir: 'node_modules/.vite-e2e', plugins: [react(), tailwindcss()], resolve: {alias: {'@clerk/clerk-react': fileURLToPath(new URL('./tests/fixtures/clerk.tsx', import.meta.url)), '@': fileURLToPath(new URL('./src', import.meta.url))}}, build: {outDir: fileURLToPath(new URL('../.audit/implementation/e2e-dist', import.meta.url)), emptyOutDir: true}, server: {host: '127.0.0.1', port: 5190, strictPort: true}, preview: {host: '127.0.0.1', port: 5190, strictPort: true}, define: {'import.meta.env.VITE_CLERK_PUBLISHABLE_KEY': JSON.stringify('pk_test_fixture'), 'import.meta.env.VITE_API_URL': JSON.stringify('http://127.0.0.1:5190')}});
