# Architecture

A single Rust binary is the source of truth. Python and Node wrappers
exist only to put that binary on `PATH` under their respective package
manager.

## Packages

```
packages/
  rust/      crate — the CLI + library. clap for parsing.
  python/    maturin-built wheel that bundles the rust binary.
  node/      thin wrapper, resolves a per-platform optional dep
             whose payload is the rust binary.
docs/        VitePress site (published to GitHub Pages).
  internals/ contributor + agent conventions (not published).
```

## Release flow

`putitoutthere.toml` declares the three artifacts and their dependency
cascade. The `Release` workflow (`.github/workflows/release.yml`) calls
the reusable workflow at `thekevinscott/putitoutthere`. Rust package changes
retrigger PyPI and npm builds via the cascade. Release globs exclude each
package's `testing-conventions.toml`, `changelog.d/`, `migrations.d/`, and
`e2e-attestations/` bookkeeping, including the Rust paths watched by its wrappers.

## CI gates

- Per-language workflow (`rust.yml`, `python.yml`, `node.yml`) runs lint + test + build with path filters.
- [`conventions.yml`](.github/workflows/conventions.yml) calls the upstream [testing-conventions workflow](https://github.com/thekevinscott/testing-conventions/blob/v0/.github/workflows/testing-conventions.yml) at `v0`; its current coverage is described below.
- `changelog.yml` enforces a changelog fragment under `docs/changelog.d/` on PRs that touch package code.
- `docs.yml` builds + deploys the VitePress site.
- `pr-monitor.yml` gates merge on the aggregate CI status.

Testing conventions cover colocated tests and source/test co-change, unit-test
isolation and mocking hygiene, one function per file, unit and changed-line
coverage, mutation testing on changed lines, integration-test layout, exclusion
of tests from built distributions, and E2E attestation freshness. Gates run
when applicable to the detected sources, distributions, and attestations.

The Python lane scans `packages/python` with upstream defaults; this binary-only
wrapper currently has no Python source files. The TypeScript lane scans
`packages/node/src` with upstream defaults.
There is no Rust conventions lane yet; Rust's separate lint/test/build workflow
does not replace those checks.

The intended template policy is upstream defaults on every lane, with no custom
`testing-conventions.toml` or exemptions, so clones inherit the full standard.

## Public-API surface

Defined in `docs/internals/repo.md`: every exported value/type, every CLI
flag, every config key, every observable artifact. Changes to that
surface require a fragment under `docs/changelog.d/` (plus
`docs/migrations.d/` when breaking).
