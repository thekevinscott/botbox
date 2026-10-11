# Backport plan — what to pull from dirsql & cachetta

**Status:** analysis + decisions only. **Nothing has been implemented.** This is
the pick-up-later doc. The grounded per-commit record is in
**`BACKPORT-LEDGER.md`**.

## TL;DR

dirsql (Rust/Py/TS) and cachetta (Py/JS) are downstream products of this
template. After template-lib's last commit (`fb70f79`, 2026-05-18) they
independently hardened the *same* areas — type-checking, coverage, test layout,
packaging. That convergence is the signal worth harvesting. Their **feature
code is not** (SQL serving, `interpret`, `Table`, config serialization; cache
`/` operator, `hash()`, `hashed=True`, literal-path semantics).

**The rubric** (this is the lens, not "did the client ship it?"):
1. Does it reduce a footgun *by default*?
2. Low ongoing maintenance for every downstream consumer?
3. Is it actually settled (not churned/reversed)?
4. Is it value-neutral, or a deliberate opinion the template owner must choose?

## Decisions on the five items discussed

### 1. `ty` for Python type-checking — **ADOPT**
- Replace `mypy` with Astral `ty`: swap `just py-typecheck` to `ty check`, add a
  `python.yml` (template name) type-check job, add empty `packages/python/.../py.typed`,
  enable ruff `PGH003` (forbid bare `# type: ignore`/`# ty: ignore`).
- **Pin `ty` tightly** — it is pre-1.0 (dirsql used `ty==0.0.42`).
- **Start clean:** do **not** copy dirsql's four baseline `# ty: ignore` TODOs. The
  template's near-empty Python package should pass `ty` outright.
- Open choice: replace mypy outright (recommended) vs. keep mypy as a second
  non-blocking gate during the pre-1.0 window.
- Source: dirsql `cd37441`; cachetta `fbacd3d`, `5c72508` (exclude `setup.py` shim from ty).

### 2. Rust branch-coverage floor — **ADOPT THE GOAL, RE-IMPLEMENT**
Verified against the tool (June 2026): cargo-llvm-cov has **no
`--fail-under-branches`** (only `--fail-under-{lines,functions,regions,file-lines}`),
and `--branch` is **unstable + nightly-only**. So a branch floor *must* be
computed by us. dirsql did this by `awk`-parsing the human `TOTAL` text row
(brittle: depends on column order/format). Re-implement by reading the **stable
JSON contract** instead, in a checked script (not an inline YAML one-liner):

```bash
#!/usr/bin/env bash   # internals/rust-cov-floor.sh
set -euo pipefail
LINE_FLOOR=90; BRANCH_FLOOR=65
json=$(cargo llvm-cov --manifest-path packages/rust/Cargo.toml --features cli \
         --branch --json --summary-only)
lines=$(jq -r '.data[0].totals.lines.percent'    <<<"$json")
branch=$(jq -r '.data[0].totals.branches.percent' <<<"$json")
printf 'lines %.2f%% (floor %d) | branches %.2f%% (floor %d)\n' \
       "$lines" "$LINE_FLOOR" "$branch" "$BRANCH_FLOOR"
fail=0
awk "BEGIN{exit !($lines  >= $LINE_FLOOR)}"  || { echo "::error::lines $lines% < $LINE_FLOOR%";    fail=1; }
awk "BEGIN{exit !($branch >= $BRANCH_FLOOR)}" || { echo "::error::branches $branch% < $BRANCH_FLOOR%"; fail=1; }
exit $fail
```

Improvements over dirsql: (a) JSON path `.data[0].totals.branches.percent` is the
stable llvm-cov export schema; (b) it's a reviewable/testable file; (c) the
nightly pin moves to a single `COV_NIGHTLY` workflow env var (or
`rust-toolchain.toml`) so the rotting date is a one-line bump. `jq` is preinstalled
on ubuntu runners. **Tradeoff to document:** a branch floor forces a nightly
dependency in the coverage job (build/test/lint stay on stable). If we don't want
nightly, the only option today is line/region floors on stable.
- Verify `.data[0].totals.branches.percent` against the pinned cargo-llvm-cov version when implementing.
- Sources: dirsql `8c7541a`, `fae6aee`; [taiki-e/cargo-llvm-cov](https://github.com/taiki-e/cargo-llvm-cov), [issue #8](https://github.com/taiki-e/cargo-llvm-cov/issues/8).

### 3. Unit/integration boundary guard — **EXTRACT TO ITS OWN PACKAGE**
*What it is:* a CI-only **repo-integrity linter for the config itself** (cachetta
`internals/check_boundary.py`, run by `internals.yaml`). It string-matches
invariants across `py-test.yaml`, `pyproject.toml`, `setup.py`, `MANIFEST.in`,
`vitest.config.unit.ts` to assert one rule: **unit coverage is measured by file
*location*, not a pytest marker** — i.e. unit tests are colocated `src/**/*_test.py`
& `src/**/*.test.ts`, `tests/` is integration, `*_test.py` is omitted from coverage
and excluded from the wheel/sdist, and nothing under `tests/` shadows a `src/` module.
It lives in `internals/` so it isn't collected by the suites it polices.

*Why package:* as written it's unportable — hardcodes `cachetta`, `py-test.yaml`,
`packages/python`, `packages/javascript`, and asserts by substring. To be reusable
it needs a rewrite from *string-matching one repo* to *config-driven structural
checks*: a `[tool.boundary-guard]` table (package dirs, workflow filename,
coverage-omit globs) parsed and asserted, not `in`-checked.

*Deeper note:* this guard exists because the layout is easy to get wrong. Package
the guard, **but also ship the location-based layout as the template default** so
the guard mostly has nothing to catch.
- Source: cachetta `e604d29`, `1982c17`, `f6e9bbd`, `a2b2e8c`.

### 4. Mock-isolation lint — **EXTRACT TO ITS OWN PACKAGE(S)**
*What it is:* two enforcers of one policy — "a unit test mocks every first-party
collaborator except the module under test and pure value modules":
- **Python** `flake8-mock-isolation` (`MIS001` unmocked import, `MIS002` test maps to
  no source module). AST-based; **already structured as an installable package**
  (own `pyproject`, `flake8.extension` entry-point) — closest to ready.
- **JS** ESLint rule `mock-isolation/collaborators` (same policy via `vi.mock` detection).

*Why package:* shipping plugin *source* into every scaffold is the maintenance
cost flagged in the audit; versioned packages fix that. Make configurable: the
Python `_roots()` assumes a single `src/<pkg>/`+`tests/` layout and hardcodes
pure-value suffixes (`exceptions`, `_sentinel`); the ESLint rule hardcodes
`constants/errors/types`.
- Source: cachetta `3090d11`, `7553112` (flake8 pin for determinism).

### 5. Mock vs DI — **mock-by-default is the house style; DI only for callback-shaped deps**
Owner dislikes DI (argument explosion); that objection is correct and dominant.
The genuine engineering position (not a reflexive defense):
- DI's real wins: type-checked & refactor-safe seams (vs. `mock.patch("pkg.mod.x")`
  coupling to an import string the type checker can't see), parallel-safe, and it
  tests behavior over implementation.
- But DI everywhere = argument explosion; mitigations (bundle deps into one
  `Deps`/context object, prod-default args, class-level injection) reduce but don't erase it.
- **Resolution:** keep **mock by default**; reach for an injected seam *only* when the
  dependency is genuinely callback/strategy-shaped (a handler, clock, writer the SUT
  already receives) or a hot-loop dep you want behind one typed contract. Keep the
  **`monkeypatch` ban** (prefer scoped `mock.patch.object`/`mocker`).
- This is essentially where dirsql landed *after* its flip (`adb919a`/`b23087f`).
  Because that policy churned/reversed, do **not** port the prose verbatim — write the
  template's own contract from the resolution above.
- Owner may opt for stricter "mock, full stop" — open question below.

## Candidate tiers (everything worth including)

**Tier A — adopt close to as-is (clean, low-risk):**
- `bundle_cli`/target-symlink cleanup — dirsql `9172f22`, `f549360` *(gated on putitoutthere version)*
- Manual `workflow_dispatch` release input — `d515dbc`
- Cache Playwright browsers in docs CI — `3782550`; Playwright bump + pr-monitor source swap — `b880a46`
- Dedicated `tsc --noEmit` type-check job — `8ae1ea2`
- pnpm-11/esbuild build-approval + trigger JS CI on `pnpm-workspace.yaml` — cachetta `67e87ad`, `08afcf8`, `73cac19`
- Pinned `flake8` for determinism — cachetta `7553112`
- Ship docs recursively *(decide the in-package bloat tradeoff first)* — cachetta `06c062d`

**Tier B — adopt the idea, re-implement for the template:**
- `ty` adoption — §1 (strip baseline; pin; clean start)
- Rust branch-coverage floor — §2 (JSON parse, centralized nightly pin)
- Location-based unit/integration layout as the **default** — cachetta `1982c17`, `29ade9d`, `f6e9bbd`
- Coverage gating — pick a deliberate floor + ratchet (NOT 100% by fiat; the repos disagree 100 vs 90/65), number-free check names, omit test files + only thin shims — `fae6aee`, `2753fe6`, `32e20a2`
- TS napi-crate layout + `cli/` directory naming + colocated tests — `47ec51b`, `630bdb0`, `95e15f5`
- biome `useBlockStatements` + pinned semicolons — `adb919a`
- `docs-check` workflow mirroring `changelog.yml` (+ `Skip-Docs:` trailer) — cachetta `b91f53f`
- AGENTS→CLAUDE/internals rules: CI-red-first (`925ed94`), coverage-floor-scope (`ede7dbf`), Imports/Manually-exercise (`d84eaad`), env-aware remote/GitHub-issue notes (cachetta `e7b6a0e`), TDD red-first (`093728e`)

**Tier C — extract to their own packages (decided):**
- Boundary guard — §3
- Mock-isolation flake8 plugin + ESLint rule — §4

**Tier D — deliberate owner decision before any port:**
- Coverage floor number (100% vs 90/65 vs ratchet)
- `requires-python >=3.11` (drops 3.10 users) — dirsql `853bace`
- Recursive-docs packaging bloat (ship docs in wheel/npm at all?)
- Mock-only vs mock-with-DI-carveout strictness (§5)

## Open questions for next session
1. `ty`: replace mypy outright, or keep mypy non-blocking until `ty` ≥ 1.0?
2. Coverage: target number + ratchet policy? Branch floor (⇒ nightly) yes/no?
3. Boundary guard & mock-isolation: one combined "template-internals" package, or
   separate per-ecosystem packages (PyPI flake8 plugin + npm eslint plugin)?
4. Recursive-docs packaging: ship docs in-package, or rely on the hosted docs site?
5. Test policy strictness: mock-by-default + DI carve-out (recommended), or mock-only?

## Provenance
- Both repos are public/MIT; reached via direct `git clone` (the session's GitHub
  MCP tools are scope-locked to `thekevinbot/template-lib`).
- Cutoff = `fb70f79` @ `2026-05-18T17:53:43Z`. dirsql ≈70 commits, cachetta = 36.
