# TypeScript — review

## Pre-review tooling pass

Before reading a line:

```fish
pnpm install
pnpm run build              # does it compile?
pnpm exec tsc --noEmit      # does it type-check?
pnpm test                   # do tests pass?
pnpm exec eslint .          # is it linted?
pnpm exec prettier --check . # is it formatted?
```

If the agent didn't run these, ask. If they fail, the agent should fix before you read.

## Reading-a-PR checklist

1. **Tooling pass** — all five green?
2. **Types** — public surface fully typed; `unknown` at boundaries, narrowed before use.
3. **Tests** — colocated `*.test.ts`, exercising the public surface; factory injection where dependencies need to be swapped.
4. **`exports` map** — `types` per condition, `sideEffects` set correctly.
5. **Barrels** — explicit named re-exports at the public boundary.
6. **`package.json` changes** — new deps match the ecosystem table in [setup.md](setup.md); `"files"` allowlist scoped to `dist` plus the staged `changelog.d`/`migrations.d` fragment folders.
7. **Reuse over reinvention** — date math, deep clone, schema validation, retry-with-backoff all come from the ecosystem table.
8. **Public API surface** — `default` vs named consistent; `@hidden` / `@internal` on the rest.
9. **Changelog fragment** — a `docs/changelog.d/` fragment added (plus `docs/migrations.d/` when breaking) for any consumer-observable change, or a `skip-changelog:` trailer present. See [../repo.md](../repo.md).
10. **`putitoutthere.toml`** — `globs` cover every source path that should cascade; polyglot CLIs declare `depends_on` on the Rust crate.

---

## Common type errors

- *"Type 'X' is not assignable to type 'Y'"* — structural mismatch. Read the message all the way down; the cause is usually nested.
- *"Property 'foo' does not exist on type 'X'"* — either a missing field, or a discriminated union to narrow.
- *"Object is possibly 'undefined'"* — null/undefined narrowing. Use `?.`, `??`, or an early return.
- *"Type 'Promise<X>' is not assignable to type 'X'"* — missing `await`.
- *"Argument of type 'X' is not assignable to parameter of type 'never'"* — exhaustiveness check failing; a union member the function doesn't handle.
- *"Cannot find module 'foo' or its corresponding type declarations"* — missing dep, missing `@types/foo`, or `moduleResolution` mismatched.
- *"This expression is not callable"* — usually a union of incompatible function shapes; narrow first.
