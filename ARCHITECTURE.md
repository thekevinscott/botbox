# Architecture

botbox is a pure-Python library. The root [README](README.md) is the spec.

## Packages

```
packages/
  python/    the `botbox` package (hatchling, src layout).
    src/botbox/agents/claude/  `ClaudeAgent` and its Dockerfile.
    src/botbox/agents/pi/      `PiAgent` and its Dockerfile.
docs/        VitePress site (published to GitHub Pages).
  internals/ contributor + agent conventions (not published).
```

## Release flow

`putitoutthere.toml` declares the one PyPI artifact. The `Release` workflow (`.github/workflows/release.yml`) calls the reusable workflow at `thekevinscott/putitoutthere`. The version comes from git tags via `hatch-vcs`.

## CI gates

- [`python.yml`](.github/workflows/python.yml) runs lint, typecheck, unit, and integration tests. E2E tests never run on CI.
- [`conventions.yml`](.github/workflows/conventions.yml) calls the upstream [testing-conventions workflow](https://github.com/thekevinscott/testing-conventions/blob/v0/.github/workflows/testing-conventions.yml) at `v0` against `packages/python`, with upstream defaults.
- `changelog.yml` enforces a changelog fragment under `docs/changelog.d/` on PRs that touch package code.
- `build-check.yml` and `check.yml` validate the release build and `putitoutthere.toml` on PRs.
- `docs.yml` builds + deploys the VitePress site.
- `pr-monitor.yml` gates merge on the aggregate CI status.

## Public-API surface

Defined in `docs/internals/repo.md`: every exported value/type, every config key, every observable artifact. Changes to that surface require a fragment under `docs/changelog.d/` (plus `docs/migrations.d/` when breaking).
