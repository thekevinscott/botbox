# Rust — shipping

## Github

Github is the source of truth.

### Github Actions

`concurrency` to cancel previous runs on the same ref:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

Cheap, always wanted.

---

## Public API design

- **`pub` is the API surface.** Anything `pub` in `lib.rs` (or re-exported through it) is a contract. Agents over-expose — scan for `pub` on things that should be `pub(crate)` or private.
- **Re-export the public surface from `lib.rs`.** `pub use` the handful of types/functions consumers need; keep paths shallow. Deep `mynewproduct::internal::detail::Thing` leaking to consumers is a smell.
- **Typed errors with `thiserror`** for libraries — one variant per failure mode, `#[error("...")]` messages. No `anyhow` in a library's public API; no `Box<dyn Error>` returned from a library.
- **`#[derive(Debug)]` on every public type.** Convention. Add `Clone` / `PartialEq` / `Eq` / `Hash` deliberately, where the type's semantics support them.
- **Doc comments (`///`) on every public item**, with a runnable example where it earns one — doc tests run under `cargo test`, so the docs can't silently rot. Prose explains *why*; the signature carries the *what*.
- **Constructors follow `new` / `with_*` / `from` / `try_*`** — `make()` / `create()` / `build_new()` are non-idiomatic.
- **`#[non_exhaustive]`** on public enums/structs that may grow — lets you add variants later without a breaking change.
- **Semver discipline.** Adding a variant to a non-`#[non_exhaustive]` public enum, changing a signature, removing a `pub` item — all breaking. The `release:` trailer must reflect it.

---

## CLI architecture

**Every CLI in this repo is a Rust binary.** The Python and Node packages are thin wrappers that put the compiled binary on `PATH` through `pip install` / `npm install -g`. Argument parsing, validation, exit codes, the whole runtime live in the crate.

Why: cross-platform distribution is a solved problem in Rust (one static binary per target), `clap` is the strongest CLI framework in any ecosystem, and one source of truth keeps argument grammar, help text, and error messages identical across every install path.

For the Rust reviewer this makes the crate the high-stakes package — the wrappers carry almost no logic; the crate carries all of it.

```
mynewproduct/
  packages/
    rust/              # binary crate — Cargo.toml, src/main.rs (clap App)
    node/              # npm wrapper — launcher resolves the per-platform binary
    python/            # PyPI wrapper — entrypoint execs the staged binary
  putitoutthere.toml
```

What to check:

- **`clap` with the derive API** — `#[derive(Parser)]` structs, not hand-rolled arg parsing.
- **`main` returns `anyhow::Result<()>`** — `?` propagates, the error prints, the process exits non-zero. No `.unwrap()` in `main`.
- **Exit codes are deliberate** — documented codes via `std::process::exit`, or `anyhow` for the catch-all non-zero.
- **The crate is tested in Rust** (`cargo test`); the wrappers ship one happy-path e2e each. CLI grammar is defined once, in `clap`.

The full three-artifact shape (Rust crate + npm wrapper + PyPI wheel) and the wrapper launchers are in [../typescript/shipping.md](../typescript/shipping.md) / [../python/shipping.md](../python/shipping.md).

---

## CI/CD

`.github/workflows/` shape:

| Workflow | Purpose | Trigger |
|---|---|---|
| `test.yml` | `cargo test` | every push/PR |
| `lint.yml` | `cargo clippy -- -D warnings` + `cargo fmt --check` | every push/PR |
| `check.yml` | `uses: thekevinscott/putitoutthere/.github/workflows/check.yml@v0` — validates `putitoutthere.toml` (parse/schema, duplicate names, `depends_on` cycles / dangling refs) | every PR |
| `build-check.yml` | `uses: thekevinscott/putitoutthere/.github/workflows/build.yml@v0` — full plan + per-target build matrix, no publish | PRs touching build inputs |
| `docs.yml` | `cargo doc` build (catches broken intra-doc links) | push to main |
| `release.yml` | `uses: thekevinscott/putitoutthere/.github/workflows/release.yml@v0` | push to main |
| `changelog-check.yml` | changelog fragment added under `docs/changelog.d/` (or `skip-changelog:` trailer) | every PR |

> **Two `check.yml`s — don't conflate them.** The workflow file named
> `check.yml` is piot's *config* gate: it validates `putitoutthere.toml`,
> not Rust source. There is no standalone `cargo check` workflow —
> `clippy` (`lint.yml`) and the release build already compile the crate,
> so a separate one would be redundant. `cargo check` stays the fast
> inner-loop command locally (see [setup.md](setup.md)). `build-check.yml`
> is piot's heavier sibling: the full release build matrix, minus publish.

```yaml
- uses: actions/checkout@v6
- uses: dtolnay/rust-toolchain@stable
  with:
    components: clippy, rustfmt
- uses: Swatinem/rust-cache@v2
- run: cargo clippy -- -D warnings
```

- **`dtolnay/rust-toolchain`**, not the deprecated `actions-rs/*` actions.
- **`Swatinem/rust-cache`** caches `~/.cargo` and `target/` — meaningful speedup.
- **`-D warnings`** on clippy in CI — warnings block merge.
- **Path filters** so docs-only PRs skip the build.
- **Concurrency** to cancel previous runs on the same ref (see Github).
- **Matrix**: Ubuntu-only for tests. Matrix on OS (Ubuntu, macOS, Windows) only for the per-target binary builds at release.

---

## Release

**Use `putitoutthere`.** Single reusable workflow, single config file, OIDC trusted publishers across crates.io / PyPI / npm. Provenance, retry-with-backoff, tag rollback, registry idempotency are all inside the workflow. CHANGELOG/MIGRATIONS philosophy is cross-cutting — see [../repo.md](../repo.md).

### `putitoutthere.toml`

Repo-root config. A crate-only package:

```toml
[putitoutthere]
version = 1

[[package]]
name          = "mynewproduct"
kind          = "crates"
crate         = "mynewproduct"
path          = "."
first_version = "0.0.1"
globs         = ["src/**", "Cargo.toml", "Cargo.lock", "LICENSE"]
```

When the crate is the core of a polyglot CLI it's the first package in the dependency graph — the npm and PyPI wrappers `depends_on` it and publish with the same version. Full three-artifact `putitoutthere.toml` is in [../python/shipping.md](../python/shipping.md) / [../typescript/shipping.md](../typescript/shipping.md).

### Reusable workflow

`.github/workflows/release.yml`:

```yaml
name: Release
on:
  push:
    branches: [main]

jobs:
  release:
    uses: thekevinscott/putitoutthere/.github/workflows/release.yml@v0
    permissions:
      contents: write
      id-token: write
```

The workflow drives `plan → build → publish → GitHub Release`. Consumer-side YAML stays at the stub above.

### Release trailer

Default cascade bump is `patch`. Override in the merge-commit body:

```
fix: handle empty input

release: minor
```

Grammar: `release: {patch|minor|major|skip} [pkg1, pkg2, ...]`. Last trailer wins. `putitoutthere` owns the version — don't hand-edit `Cargo.toml`.

### Trusted publishers

One-time crates.io setup: publish once via classic `cargo publish`, then enable trusted publishing under `https://crates.io/crates/<crate>/settings`. After that the workflow authenticates via OIDC only — no long-lived registry token in CI.

---

## Docs

**`cargo doc` is the API reference.** `///` doc comments compile to HTML; published crates land on `docs.rs` automatically with no extra config.

- **Doc tests run under `cargo test`** — examples in `///` blocks are verified, so they can't drift from the code.
- **`#![warn(missing_docs)]`** at the crate root makes an undocumented `pub` item a warning — pair with `-D warnings` in CI to make it block merge.
- **`//!` module-level docs** at the top of `lib.rs` and each module — the crate's front page on docs.rs.
- For a richer prose doc *site* (guides, not just API reference), `mdBook` is the standard. Most crates don't need it — `cargo doc` plus a good README is enough.
