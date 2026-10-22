# Agent contract

This file is the operating contract for AI agents working in this repo.
Conventions, supervision rules, and per-language style live under
`docs/internals/` — start there before making changes.

## Where to read first

- `docs/internals/repo.md` — cross-cutting rules (changelog/migration fragment philosophy, public-API surface, CI-logic-in-scripts).
- `docs/AGENTS.md` — the docs site's pages.
- `docs/internals/python/` — Python style, testing, shipping, review, setup.

## Package layout

- `packages/` holds public-facing packages published to a registry.
- `internals/` holds internal-only packages, built and tested to the same
  standards but never published. Private workspaces that only produce build
  artifacts for a published package belong here too.

## Workflow

- Use `just` for local tasks (`just lint`, `just test`, `just ci`).
- `just test-e2e` reads `.env` from the checkout root. In a worktree under
  `.worktrees/<name>/`, symlink it first: `ln -s ../../.env .env`.
- Run only the e2e files your change touches, and attest that subset (from
  `packages/python`): `testing-conventions e2e attest 'uv run --env-file
  ../../.env pytest tests/e2e/run_test.py'`. Commit the receipt with the code
  before pushing; a receipt pushed on its own reruns all of CI. e2e runs
  collide, so run one at a time.
- Unit tests are **colocated** with their source (`foo.py` ↔ `foo_test.py`).
  This is the
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

1. **Repo must be public.** PyPI Trusted Publishing requires the provider
   to inspect the workflow file at the configured ref; private repos cannot
   satisfy this. The `preflight` job in `.github/workflows/release.yml` fails
   fast if the repo is private.
2. **Register a PyPI Trusted Publisher** (a pending publisher for a brand-new
   project). putitoutthere's
   [first-release guide](https://github.com/thekevinscott/putitoutthere/blob/main/.claude/skills/first-release/reference/trusted-publishers.md)
   has the steps.

## Out of scope

- Don't add unsolicited refactors or hypothetical-future abstractions.
- Don't bypass hooks or CI gates without an explicit reason in the PR body.

@docs/internals/session-handoff.md
