# Agent contract

This file is the operating contract for AI agents working in this repo.
Conventions, supervision rules, and per-language style live under
`docs/internals/` — start there before making changes.

## Where to read first

- `docs/internals/repo.md` — cross-cutting rules (changelog/migration fragment philosophy, public-API surface, CI-logic-in-scripts).
- `docs/AGENTS.md` — how the docs site is organized ([Diataxis](https://diataxis.fr)) and the per-page quadrant rule.
- `docs/internals/rust/` — Rust style, testing, shipping, review, code-smells.
- `docs/internals/python/` — Python style, testing, shipping, review, setup.
- `docs/internals/typescript/` — TypeScript style, testing, shipping, review, setup.

## Package layout

- `packages/` holds public-facing packages published to a registry.
- `internals/` holds internal-only packages, built and tested to the same
  standards but never published. Private workspaces that only produce build
  artifacts for a published package belong here too.
- The root-level `ci/` package is an exception: CI logic stays there under the
  workflow policy below.

## Workflow

- Use `just` for local tasks (`just lint`, `just test`, `just ci`).
- Unit tests are **colocated** with their source (`foo.py` ↔ `foo_test.py`,
  `foo.ts` ↔ `foo.test.ts`; Rust uses inline `#[cfg(test)]`). This is the
  [testing-conventions](https://github.com/thekevinscott/testing-conventions)
  standard, enforced in CI by `.github/workflows/conventions.yml`.
- **CI logic lives in scripts, not workflow YAML.** `run:` / `github-script`
  steps stay trivial glue; anything with iteration, `case` dispatch, or
  text-munging moves to a tested script invoked as a one-liner. Enforced by
  testing-conventions' `workflow-lint` check
  (`.github/workflows/workflow-lint.yml`); the bright line and rationale are in
  `docs/internals/repo.md`.
- Every PR that changes a public API adds a **changelog fragment**: one
  timestamped file under `docs/changelog.d/` (plus one under
  `docs/migrations.d/` for breaking changes), named `YYYY-MM-DD-<pkg>-<slug>.md`
  by UTC merge date. The folders are the permanent, append-only record;
  `packages/<pkg>/CHANGELOG.md` / `MIGRATIONS.md` are pointer stubs — never
  append entries to them. For version attribution ("which release shipped X"),
  map fragment dates against tags via `git log --tags`. Enforced by
  `.github/workflows/changelog.yml`. Bypass with a `skip-changelog:` git
  trailer for genuinely internal refactors.
- Pre-commit hooks (`just hooks` to install) gate formatting, gitleaks, and per-language linters.

## First-publish prerequisites

Before the first `Release` run on a fresh scaffold:

1. **Repo must be public.** Trusted Publishing on npm / PyPI / crates.io
   requires the provider to inspect the workflow file at the configured
   ref; private repos cannot satisfy this. The `preflight` job in
   `.github/workflows/release.yml` fails fast if the repo is private.
2. **`NPM_TOKEN` and `CARGO_REGISTRY_TOKEN` set as repo secrets.** npm
   and crates.io Trusted Publishing bind to an already-published package,
   so the first publish needs a long-lived token. `release.yml` forwards
   both to the putitoutthere reusable workflow, which publishes with them
   when set. Easy to forget — without `NPM_TOKEN` the first npm publish
   404s. The npm token must bypass 2FA for writes (a classic Automation
   token, or a granular token with "Bypass 2FA" enabled), or the publish
   fails with `EOTP`.
3. **After the first publish, switch to Trusted Publishing.** Register a
   Trusted Publisher for every published package (each npm per-platform
   sub-package needs its own), then delete both secrets. putitoutthere's
   [first-release guide](https://github.com/thekevinscott/putitoutthere/blob/main/.claude/skills/first-release/reference/trusted-publishers.md)
   has the per-registry steps.

## Out of scope

- Don't add unsolicited refactors or hypothetical-future abstractions.
- Don't bypass hooks or CI gates without an explicit reason in the PR body.

@docs/internals/session-handoff.md
