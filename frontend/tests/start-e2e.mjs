// Build the test-only Clerk/API configuration into an isolated artifact folder.
// Serve compiled assets, avoiding development HMR/module-loading races.
import { build, preview } from 'vite';
import { fileURLToPath } from 'node:url';

const configFile = fileURLToPath(new URL('../vite.e2e.config.ts', import.meta.url));
await build({configFile});
await preview({configFile});
