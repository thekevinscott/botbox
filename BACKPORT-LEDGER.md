# Backport ledger — dirsql & cachetta → template-lib

Every commit landed in `thekevinscott/dirsql` and `thekevinscott/cachetta`
*after* template-lib's most recent commit, with the files it touched and the
**salient bits worth keeping** (i.e. what, if anything, is a candidate to pull
back into this template). The forward-looking decisions and re-implementation
notes live in the companion **`BACKPORT-PLAN.md`** — this file is the raw,
grounded record.

- **Cutoff:** template-lib `fb70f79` ("Document first-publish prereqs…"),
  2026-05-18 13:53 -0400 / `2026-05-18T17:53:43Z`.
- **Why these repos matter:** both were scaffolded *from* this template, so the
  question per commit is "is this a reusable scaffolding/tooling/convention
  change (keep) or project feature code (drop)?"
- **Filename mapping** (downstream → template) when porting CI:
  `rust-test.yml→rust.yml`, `python-test.yml→python.yml`, `ts-test.yml→node.yml`,
  `docs-test.yml→docs.yml`, `changelog-check.yml→changelog.yml`. cachetta uses
  `packages/javascript` (template: `packages/node`) and `*.yaml` workflow names.
- **Verdict key:** ✅ keep (reusable) · 🟡 partial (extract reusable part, drop
  project code) · ❌ drop (project-specific feature/docs/release churn).

Merge commits are omitted (their content is in the child commits listed).

---

## dirsql

### PR #182 — release fix
- `9172f22` **fix(release): drop packages/rust/target symlink (crates.io 413)** — ✅
  *Touched:* `.gitignore`, `CHANGELOG.md`, `packages/rust/target` (symlink delete), `putitoutthere.toml`.
  *Keep:* removal of the tracked `target` symlink hack + the `[package.bundle_cli]`
  `crate_path` simplification. `cargo publish` was following the symlink and
  archiving a ~133 MiB `.crate` → crates.io 413. **Depends on** putitoutthere #337
  being in the template's pinned version before porting the removal.

### PR #181 — CLI docs audit
- `d9d3c89` docs: consolidate CLI docs — ❌ (dirsql docs content + vitepress config)
- `8c4ffb3` docs: trim low-value docs tests — ❌ (dirsql docs tests)
- `5d49e07` ci: re-trigger precheck — ❌ (empty no-op, 0 files)

### PR #183 — release 0.3.6
- `81ad5d1` chore(release): cut 0.3.6 — ❌ (`CHANGELOG.md`, `Cargo.toml` version bump)
- `853bace` **fix(py): drop Python 3.10 (requires-python >=3.11)** — 🟡
  *Touched:* `CHANGELOG.md`, `MIGRATIONS.md`, `packages/python/pyproject.toml`.
  *Keep:* the `requires-python` floor *as a deliberate owner choice* (drops 3.10 users); the CHANGELOG/MIGRATIONS text is project-specific.

### PRs #184/#185 — `extract` callback + default `files` table
- `925ed94` **Require CI to go red for the right reason before implementing** — ✅
  *Touched:* `AGENTS.md`. *Keep:* the red/green discipline rule (adapt into `AGENTS.md`/`internals/`).
- `84d6ed6` test: binary file under a glob (RED) — ❌ (`packages/rust/tests/sdk.rs`)
- `caa7fec` test: rustfmt the RED test — ❌
- `ba0922d` Drop `content` from `extract` callback — ❌ (cross-language API change; 30+ src/test/doc files)
- `9901392` test: ruff format — ❌
- `140f0ce` test: zero-config serves `files` table (RED) — ❌ (`cli_e2e.rs`)
- `4feecad` Serve default `files` table — ❌ (`src/bin/dirsql.rs` feature + docs)
- `1aca957` / `eaff02b` Update config.md / server.md — ❌ (docs content)

### PR #187 — manual release
- `d515dbc` **feat(ci): manual release via release_packages workflow_dispatch input** — ✅
  *Touched:* `.github/workflows/release.yml`. *Keep:* the `workflow_dispatch` input
  forwarded to the putitoutthere reusable workflow — clean release ergonomics, low risk.

### PR #190 — release fix
- `f549360` **fix(release): declare [package.bundle_cli] for dirsql-npm (musl)** — 🟡
  *Touched:* `CHANGELOG.md`, `putitoutthere.toml`. *Keep:* the npm `bundle_cli`
  declaration pattern so the upstream musl path fires; package names are project-specific.

### PR #200 — TS crate reorg
- `47ec51b` **Reorganize TS package: move napi binding to separate crate** — 🟡
  *Touched:* `changelog-check.yml`, `rust-test.yml`, `.gitignore`, `AGENTS.md`,
  `ARCHITECTURE.md`, root `Cargo.toml`, and a large `packages/ts/**` move
  (`napi/` crate, `src/bin/`, `src/`, configs).
  *Keep:* the **layout convention** — nest the napi binding crate under
  `packages/ts/napi`, pure-TS package with `src/` layout, plus the matching CI
  path-filter / changelog-glob / workspace-member updates. The file moves are dirsql's.

### PR #206 — rust branch coverage
- `8c7541a` **ci(rust): gate branch coverage on nightly** — 🟡 (keep the *goal*, not the impl)
  *Touched:* `.github/workflows/rust-test.yml`. *What it does:* moves only the
  coverage job to a **pinned nightly** (`nightly-2026-05-28`), adds `--branch`, and
  — because cargo-llvm-cov has **no `--fail-under-branches`** — gates the branch
  floor by `awk`-parsing the text `TOTAL` row. *Keep the intent* (a branch floor);
  **re-implement** via JSON parse + centralized nightly pin (see BACKPORT-PLAN §2).

### PR #201 — coverage floors
- `fae6aee` **test: raise coverage floors honestly (Rust/Py/TS)** — 🟡
  *Touched:* all three test workflows + `pyproject.toml` + many `packages/rust/src|tests` + ts test/config files.
  *Keep:* `--cov-branch` at 100% (Py), vitest 100% thresholds, **number-free check
  names**, and the **coverage-omit convention** (omit `*_test.py`/`*.test.ts`, omit only
  the thin `bin` shim — not whole modules). The bulk new tests are project code.
- `0bd9e3c` docs(python): refresh coverage-omit comment — ❌ (comment only)

### PR #197 — config serialization (feature)
- `4fb8384` red integration tests — ❌ · `bff9284` feat serialization — ❌ ·
  `caba7f5` serialize eagerly/drop ready() — ❌ · `0b52b2f` tighten resolver — ❌ ·
  `80304de` extract resolver module — ❌ · `b5e478f` rename `_resolve.py` — ❌ ·
  `58d04b5` docs trim — ❌
- `95e15f5` **colocated unit tests for resolve_config** — 🟡
  *Keep:* the **colocated `*_test.py` / `*.test.ts` layout** convention; the tests themselves are dirsql.

### PR #210 — cli rename
- `630bdb0` **rename: `_cli/` (Py) & `src/bin/` (TS) → shared `cli/`** — 🟡
  *Touched:* `CHANGELOG/MIGRATIONS`, `conftest.py`, `packages/python/dirsql/cli/*`,
  `pyproject.toml`, `packages/ts/**` + `vitest.config.ts`.
  *Keep:* the cross-language **`cli/` directory name** + the coverage/`bin` path updates.

### PR #211/#214 — coverage seams, test boundaries, biome
- `5173442` **drop CLI launcher coverage excludes; DI seams + unit tests** — 🟡
  *Touched:* `AGENTS.md`, `CHANGELOG.md`, `packages/python/dirsql/cli/*`, ts cli files, both vitest configs.
  *Keep:* the **Test-Boundaries rewrite** + narrowing coverage omit to only the `bin` shim. Launcher tests are dirsql's.
- `adb919a` **style(ts): enforce useBlockStatements; flip AGENTS.md to prefer mock > DI** — 🟡
  *Touched:* `AGENTS.md`, `packages/ts/biome.json`, ts cli/test files.
  *Keep:* the **biome** `useBlockStatements` + pinned `semicolons:"always"`. The
  **mock>DI policy flip is contested and was later reversed-in-spirit** — see
  BACKPORT-PLAN §5; do **not** port the policy wholesale.
- `b23087f` refactor: drop launcher DI seams; use mock.patch.object / vi.mock — 🟡
  *Keep:* only the `monkeypatch`-ban convention; the launcher code/tests are dirsql's.

### PR #215 — type-checking tooling
- `cd37441` **feat(python): strict type-checking with ty + baseline** — ✅ (mechanism) / ⚠️ (baseline)
  *Touched:* `python-typecheck.yml`, `CHANGELOG`, `PARITY.md`, `pyproject.toml`,
  `dirsql/_dirsql.pyi`, **`py.typed`**, plus baselined source.
  *Keep:* the workflow + `[tool.ty]` config + ruff `PGH003` + `py.typed`/PEP 561.
  **Drop** the four baseline `# ty: ignore` TODOs — a scaffold starts clean.
  `ty==0.0.42` is pre-1.0; pin tightly. **Decision: adopt (see PLAN §1).**
- `8ae1ea2` **feat(ts): dedicated `tsc --noEmit` type-check job** — ✅
  *Touched:* `ts-typecheck.yml`, `CHANGELOG`. *Keep:* the fast standalone type-check job.

### PR #209 — `dirsql interpret` subcommand (feature)
- `f00c963`/`ed4501a`/`a93f70b`/`43def75`/`afc3df1` red tests + fixtures — ❌
- `8c02b19` feat interpret — ❌ · `e8982ed`/`2eab89c`/`a61f69b` fixes — ❌
- `8be9df0` wrap if-bodies in blocks — ❌ (conforms to biome rule already captured in `adb919a`)
- `e596bf6` split interpret into modules + unit tests — ❌ (feature module split)
- `9c40fef` lint/test plumbing — ❌ · `6cd5e6c` ty narrowing — ❌ · `5dc9917` PyTable.name optional — ❌
- `ede7dbf` **docs(agents): "coverage floor = unit tests only"** — ✅ (`AGENTS.md` rule, keep)
- `d84eaad` **refactor(cli): relative imports + AGENTS sections** — 🟡
  *Keep:* the `AGENTS.md` "Imports" + "Manually Exercise New Features" sections; the code is dirsql's.

### PR #216 — `Table` export (feature)
- `098eefd` red test — ❌ · `c8dd2ad` feat `Table` class export — ❌

### PR #192 — native config dispatch (feature)
- `27ed637` **red CLI integration tests for native-language config** — 🟡
  *Touched:* `python-test.yml`, `PARITY.md`, fixtures, `packages/ts/package.json`.
  *Keep:* the **"build the native binary before integration tests"** CI step + the
  wireit `tsc` test dependency; fixtures/tests are dirsql's.
- `fc5737e` **feat(cli): Rust binary dispatches `--config .{py,js,mjs,cjs}`** — 🟡
  *Touched:* `python-test.yml`, `rust-test.yml`, `CHANGELOG`, src + tests.
  *Keep:* only the python.yml binary-build step; rust functions-floor lowering + the feature are dirsql's.

### PR #218 — code review findings (feature)
- `89c735c` red tests — ❌ · `fddccda` fix rust findings — ❌ · `4a45ceb` cargo fmt — ❌ ·
  `d50f847` empty retrigger — ❌

### PRs #221 / #223 / #220 — docs CI + misc
- `3782550` **ci(docs): cache Playwright browsers** — ✅
  *Touched:* `.github/workflows/docs-test.yml`. *Keep:* `actions/cache@v4` on
  `~/.cache/ms-playwright` keyed on the docs lockfile.
- `b880a46` **ci: bump Playwright 1.60.0 + swap pr-monitor source** — ✅
  *Touched:* `pr-monitor.yml`, `docs/package.json`, `docs/pnpm-lock.yaml`.
  *Keep:* the `pr-monitor` action-source swap to `thekevinscott/pr-monitor@v1` + Playwright bump.
- `e237d64` docs(cli): document native-language config — ❌ (docs content)

---

## cachetta

### PR #51 — agent environment docs
- `e7b6a0e` **docs: environment-aware agent notes + GitHub-issue workflow** — 🟡
  *Touched:* `.gitignore`, `AGENTS.md`, `notes/agents.md`, `notes/environments/{agents,remote}.md`.
  *Keep:* the **AGENTS.md / `notes/` split** + remote-session/GitHub-issue workflow discipline; some notes are cachetta-specific.

### PR #47 — `/` operator (feature)
- `d1ac201` failing tests — ❌ · `150ab8f` feat `/` operator callables + subfolders — ❌ (`cachetta.py` + CHANGELOG)

### PR #52 — docs-check workflow
- `b91f53f` **chore: require docs updates for public-facing src changes** — 🟡
  *Touched:* `.github/workflows/docs-check.yaml`, `AGENTS.md`, `docs/python.md`, `README.md`.
  *Keep:* a **`docs-check` workflow** mirroring `changelog.yml`, with a `Skip-Docs:` trailer + policy text. Docs/README content is cachetta's.

### PR #53/#54 — pnpm 11 / esbuild
- `67e87ad` **fix: approve esbuild builds for pnpm 11** — ✅ (`pnpm-workspace.yaml` `allowBuilds` map)
- `08afcf8` **ci: trigger JS workflows on pnpm-workspace.yaml changes** — ✅ (add to JS workflow path filters)
- `73cac19` **chore: standardize on pnpm 11+, drop pnpm-10 build-approval shim** — ✅ (drop dead `onlyBuiltDependencies`)

### PR #56 — ship docs recursively
- `093728e` **red integration tests for nested docs packaging** — 🟡
  *Touched:* `AGENTS.md`, `docs/_test/nested.md`, both `CHANGELOG`s, packaging tests.
  *Keep:* the **packaging-test pattern** + the `AGENTS.md` TDD red-first section; fixtures are cachetta's.
- `06c062d` **fix: ship docs/ recursively in npm + PyPI** — ✅
  *Touched:* `packages/python/pyproject.toml`, `scripts/sync-docs.sh`.
  *Keep:* `sync-docs.sh` recursion + pyproject `docs/**/*.md` glob. **Flag the tradeoff:** this bloats every published artifact — decide if a library template should ship docs in-package at all.

### PR #61 — strict ty gate
- `fbacd3d` **chore: add strict ty type-checking gate** — 🟡
  *Touched:* `py-typecheck.yaml`, `packages/python/Makefile`, `pyproject.toml`, + source diagnostic fixes.
  *Keep:* the workflow + `[tool.ty]` config + Makefile target (cross-checks dirsql's ty adoption). Source fixes are cachetta's.

### PR #62 — 100% unit patch coverage + floor
- `2753fe6` **ci: enforce 100% unit patch coverage + non-regression floor** — 🟡
  *Touched:* `js-test.yaml`, `py-test.yaml`, `AGENTS.md`, `.gitignore`s, `package.json`,
  `vitest.config.unit.ts`, `pyproject.toml`, `pnpm-lock.yaml`.
  *Keep:* the diff-cover gate, vitest/pytest coverage config, `Skip-Coverage:` trailer,
  coverage gitignore. **Note the disagreement:** cachetta mandates 100%, dirsql uses
  90/65 — pick a deliberate floor in the template (see PLAN §2/§coverage).

### PR #66 — 100% incl. branches
- `32e20a2` **ci: require 100% unit coverage incl. branches** — 🟡
  *Touched:* `js-test.yaml`, `py-test.yaml`, `AGENTS.md`, many backfilled `*.test.ts`/`*_test.py`, `vitest.config.unit.ts`.
  *Keep:* the branch-threshold config; the backfilled tests are cachetta's.

### PR #70 — mock-isolation lint
- `3090d11` **test: enforce unit-test mock isolation via lint** — 🟡 → *extract to its own package*
  *Touched:* `eslint-rules/mock-collaborators.js`, `eslint.config.js`, `.flake8`,
  `Makefile`, `pyproject.toml`, **`tools/flake8_mock_isolation/{flake8_mock_isolation.py,pyproject.toml}`**, + reclassified tests.
  *Keep:* both enforcers (flake8 `MIS001/MIS002` + ESLint `mock-collaborators`). **Decision: package these** (see PLAN §4). Hardcoded assumptions (single `src/<pkg>/`, pure-value module names) must become config.

### PR #72 — flake8 pin
- `7553112` **chore: pin flake8 for deterministic lint gate** — ✅ (exact pin in `pyproject.toml`)

### PR #58 — public `hash()` (feature)
- `76e9034` red tests — ❌ · `527774e` feat expose `hash()` — ❌ (`hash.py`/`hash.ts` + docs)

### PR #48 — literal-path semantics (feature)
- `f5dcc79` red tests — ❌ · `0b79bc4` feat remove implicit sibling-hash rewriting — ❌ ·
  `cc20a4a` update subfolder tests — ❌

### PR #75 — colocation + boundary guard
- `1982c17` **ci(python): gate unit coverage on src/ colocated tests** — ✅ (`py-test.yaml` gates by location not marker)
- `29ade9d` **test(python): relocate unit tests into src/ colocation** — 🟡
  *Keep:* the colocation layout + pyproject/Makefile config; moving cachetta's own test files is project work.
- `f6e9bbd` **build(python): keep colocated `*_test.py` out of wheel/sdist** — ✅ (`MANIFEST.in` + `setup.py` shim)
- `e604d29` **ci: add internals/ boundary guard** — 🟡 → *extract to its own package*
  *Touched:* `.github/workflows/internals.yaml`, `internals/README.md`, `internals/check_boundary.py`.
  *Keep:* the guard concept; **package it** with config-driven paths (see PLAN §3). As written it hardcodes `cachetta`, `py-test.yaml`, package dirs.
- `a2b2e8c` **docs: define unit/integration boundary by location (AGENTS.md)** — ✅ (convention text)
- `5c72508` **build(python): exclude setup.py build shim from ty** — ✅ (`[tool.ty]` exclude)

### PR #73 — `hashed=True` flag (feature)
- `e90fbe1` red tests — ❌ · `ba2fd2d` feat honor `hashed=True` — ❌ (`cachetta.py`/`Cachetta.ts` + docs)

---

## Tally

- **dirsql:** ~12 commits carry reusable bits (✅/🟡); the remainder are feature
  PRs (#194 serialization, #196 interpret, #216 Table, #218 review, #184 extract/files) or release/docs churn.
- **cachetta:** ~16 commits carry reusable bits; features (#47, #58, #48, #44/#73) drop out.
- **Convergence signals** (both repos did it independently): strict `ty`,
  location-based unit/integration split, raised coverage gates, colocated tests.
  Treat convergence as a *hint*, not proof — they **disagree** on the coverage
  number (cachetta 100% vs dirsql 90/65), which is exactly the kind of thing the
  template must decide deliberately rather than copy.
