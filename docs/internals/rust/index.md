# Rust — agent-supervision guide

`rustup`-managed toolchain, `cargo` for build/test/lint, `clippy` as the main supervision tool with `bacon` for watch. Typed errors via `thiserror` in libraries, `anyhow` only in binaries, ownership and the borrow checker for compile-time memory safety. CLIs ship as a Rust crate; Python and Node packages are thin wrappers.

## Sub-docs

- [setup.md](setup.md) — toolchain, commands, watch mode, project shape, `Cargo.toml`, ecosystem cheat sheet
- [style.md](style.md) — reading vocabulary, foundational concepts, idiomatic patterns, memory model
- [testing.md](testing.md) — inline `#[cfg(test)]` tests, doc tests, integration tests
- [shipping.md](shipping.md) — Github, public API design, CLI architecture, CI/CD, release, docs
- [review.md](review.md) — pre-review tooling pass, reading-a-PR checklist, compiler error vocabulary
- [code-smells.md](code-smells.md) — **review-only.** The full smell catalog. Load it when reviewing agent output, not when generating code — naming bad patterns in a generation context primes them.

Cross-cutting repo conventions (changelog/migration fragment philosophy) live in [../repo.md](../repo.md).

## One-paragraph summary

`rustup`-managed toolchain, `cargo` for build/test/lint, `clippy` as the main supervision tool with `bacon` for watch. Ownership and the borrow checker mean no GC and compile-time-proven memory safety; reading Rust well is mostly reading borrows (`&T` / `&mut T`), `Result` / `Option`, and `?` propagation. Good agent output: typed errors via `thiserror` in libraries, `anyhow` only in binaries, `&str` / `&[T]` parameters over owned, idiomatic `new` / `with_*` / `from` / `try_*` constructors, inline `#[cfg(test)] mod tests`, no `.unwrap()` or `unsafe` outside FFI. Project conventions parallel the other two language docs: Github is the source of truth, `putitoutthere` drives cross-registry releases from `putitoutthere.toml` and a short reusable workflow, a changelog fragment under `docs/changelog.d/` on every consumer-observable change (philosophy in [../repo.md](../repo.md)), CI runs clippy/fmt/test as separate jobs with path filters. Every CLI is a Rust crate with `clap` — the Python and Node packages just put the binary on `PATH`, so the crate is the high-stakes package to review. Before any line-by-line read: `cargo check`, `cargo clippy`, `cargo test`, `cargo fmt --check` all green.
