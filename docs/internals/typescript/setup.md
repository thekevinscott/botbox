# TypeScript — setup

- Node 24
- pnpm

Engines pinned in root `package.json`:

```json
"engines": { "node": ">=24.0", "pnpm": ">=11" }
```

## Common Libraries

- vitest for testing
- eslint
- prettier
- tsc & tsx

**Package management is `pnpm`.** Lockfile is `pnpm-lock.yaml`; CI installs with `pnpm install --frozen-lockfile`. Never `npm` or `yarn` in a pnpm repo — the lockfiles aren't interchangeable, and `npm install` will silently rewrite resolution. The one exception worth knowing: `npm publish --provenance` is the only way to get build provenance attestations as of 2026, so projects that publish with provenance use `npm publish` at release time only.

## Watch mode

For larger packages, run vitest in watch and a parallel `tsc --watch --noEmit` in another pane. There is no single bundled watcher in idiomatic TS the way `bacon` is in Rust — you compose your own from `vitest`, `tsc -w`, and (rarely) `concurrently` / `nodemon` if you need to chain.

---

## Monorepo shape

The dominant pattern across all four audit repos is **pnpm workspaces orchestrated by [wireit](https://github.com/google/wireit)**. Wireit lives in the root `package.json` under a `"wireit"` key, with each script declared `"wireit"` in `"scripts"`:

```json
{
  "scripts": {
    "build": "wireit"
  },
  "wireit": {
    "build": {
      "dependencies": ["./packages/foo:build", "./packages/bar:build"]
    }
  }
}
```

Workspace declaration (`pnpm-workspace.yaml`):

```yaml
packages:
  - 'packages/**'
  - 'docs'
  - '!**/tmp/**'
  - '!**/node_modules/**'
```

Conventions worth adopting:

- **Real library packages live in `packages/`.** Private tooling/build/test helpers go in `internals/` and are marked `"private": true`.
- **Internal cross-package deps use `"workspace:*"`**, not version numbers. pnpm rewrites these at publish time.

---

## Per-package layout

Canonical shape (`packages/<name>/`):

```
src/
  index.ts            # public entry — re-exports only
  <feature>.ts
  <feature>.test.ts   # colocated unit tests, *.test.ts
dist/                 # emitted, gitignored
test/integration      # integration tests. _Never_ integration test the CLI, only the TS SDK. Mock third party dependencies
test/e2e              # e2e tests. Generally should test the CLI if one is available. No mocking. Not executed by CI
package.json
tsconfig.json         # extends root
README.md
CHANGELOG.md          # pointer stub — the record is docs/changelog.d/ (see ../repo.md)
MIGRATIONS.md         # pointer stub — the record is docs/migrations.d/
putitoutthere.toml
```


`package.json` exports:

```json
{
  "type": "module",
  "main": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "import": "./dist/index.js"
    }
  },
  "files": ["dist", "LICENSE", "changelog.d", "migrations.d"],
  "sideEffects": false
}
```

Things worth getting right:

- **`"type": "module"`** — ESM-only. No dual CJS build.
- **`"files"` allowlist** — `["dist", ...]`. Explicit allowlist keeps `.env`, `tmp/`, `coverage/` out of the published tarball.

Test colocation (`src/foo.ts` + `src/foo.test.ts`) is the default.

---

## TypeScript configuration

Thin root, layered per package. The root sets *strictness*, packages set *outputs*:

Root `tsconfig.json`:

```json
{
  "compilerOptions": {
    "lib": ["ESNext"],
    "target": "ESNext",
    "module": "nodenext",
    "moduleResolution": "nodenext",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "verbatimModuleSyntax": true
  }
}
```

Per-package `tsconfig.json`:

```json
{
  "extends": "../../tsconfig.json",
  "compilerOptions": {
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "outDir": "./dist",
    "rootDir": "./src",
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["./src/**/*.ts"],
  "exclude": ["node_modules", "dist", "./src/**/*.test.ts"]
}
```

A separate `tsconfig.eslint.json` is common — lint includes test files, build doesn't.

**Do not use project references (`"references"`, `composite: true`)**. They rely on wireit's dependency graph and built `dist/` outputs. The trade-off: project references make `tsc -b` work as one command, but require careful `composite: true` config and slower incremental setup.

`strict: true` is non-negotiable. If you need to disable a specific strict flag (rare — `strictPropertyInitialization` for class-based ORM models is a real case), do it once at root with a comment, not scattered per file.

---

## Ecosystem cheat sheet

Standard tooling. If the agent picks something off-brand for one of these tasks, ask why.

| Task | De facto choice |
|---|---|
| Package manager | `pnpm` |
| Test runner | `vitest` |
| Build (library) | `tsc` direct, or `tsup` |
| Type checker | `tsc` (`tsc --noEmit`) |
| Linter | `eslint` + `@typescript-eslint/*` |
| Formatter | `prettier` |
| Docs | `vitepress` (simple) / `docusaurus` (rich) |
| API reference | `typedoc` (+ `typedoc-plugin-markdown`) |
| Versioning + release | `putitoutthere` |
| HTTP client | native `fetch` (built-in since Node 18); `undici` for advanced cases |
| Schema validation | `zod` |
| Date | `date-fns` or `temporal-polyfill` |
| Logger | `pino` |
| CLI args (inside a Rust core) | `clap` |
| CLI args (TS-only utility, no Rust core) | `commander` / `cac` |
| Async iteration | native `for await ... of` |
| Rust bindings | `napi-rs` |
