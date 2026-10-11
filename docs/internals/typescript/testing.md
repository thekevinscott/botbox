# TypeScript — testing

**Default to Vitest.**

Per-package config (`vite.config.ts`):

```ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    include: ['src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'lcov'],
      thresholds: { lines: 80, functions: 80, branches: 75, statements: 80 }
    }
  }
});
```

**Integration tests** at `test/integration/` consume the *built* artifact, not source. Catches breaks (export-map drift, missing files, bad shebang on bin scripts) that source-only tests miss.

**Mocking**: use **factory injection**. Pass dependencies as constructor args; tests pass fakes:

```ts
// src/widget.ts
export function getWidget({ load, run }: Deps) {
  class Widget {
    constructor(opts: WidgetOptions) { /* ... */ }
    execute(input: Input) { /* uses load, run */ }
  }
  return Widget;
}

// src/index.ts
import { load } from './load';
import { run } from './run';
export const Widget = getWidget({ load, run });

// src/widget.test.ts
import { getWidget } from './widget';
const Widget = getWidget({ load: fakeLoad, run: fakeRun });
```

Factory injection works identically in every test runner and keeps the test plumbing visible at the call site.
