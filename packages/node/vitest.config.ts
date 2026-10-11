import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

// Lives at the package root (not under src/) so the testing-conventions
// location check — which scans src/ — never treats it as an untested source
// file. Unit tests are colocated with their subject as `*.test.ts`. `root` is
// pinned because the coverage gate runs vitest from src/.
export default defineConfig({
  root: fileURLToPath(new URL('.', import.meta.url)),
  test: {
    include: ['src/**/*.test.ts'],
  },
});
