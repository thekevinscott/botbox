# Rust — setup

## Toolchain (one-time)

Install via `rustup`:

```fish
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

Use `rustup` — never `brew install rust`, which gives a static install with no toolchain management.

This installs:
- `rustup` — toolchain manager
- `rustc` — compiler
- `cargo` — build / dep / test / run
- `rustfmt`, `clippy` — formatter and linter

## Commands you'll use

| Command | Purpose | When |
|---|---|---|
| `cargo new <name>` | New project | Starting fresh |
| `cargo check` | Type-check only, no codegen | **Inner loop** — fastest feedback |
| `cargo clippy` | Lint (check + ~700 idiom checks) | **Main supervision tool** |
| `cargo test` | Run tests | Verifying |
| `cargo run` | Compile + run | Executing locally |
| `cargo build --release` | Optimized build | Shipping |
| `cargo fmt` | Auto-format | Before committing |
| `cargo add <crate>` | Add dependency | Avoid hand-editing `Cargo.toml` |

## Watch mode

```fish
cargo install --locked bacon
cd <project>
bacon clippy     # default to clippy as the watch target
```

Use **`bacon`**, not `cargo-watch` (its own README says it's "on life support" and points users at bacon).

Press `c` for clippy, `t` for test, `w` for clippy-all, `q` to quit. `bacon.toml` per-project config supported, hot-reloaded.

> **Note**: don't run `bacon` *and* let the agent run `cargo check` at the same time — they'll fight over Cargo's project lock. Pick one. Most agent setups expect the agent to invoke cargo itself; bacon is for *you* watching in parallel.

---

## Project shape

```
mynewproduct/
├── Cargo.toml          # manifest: deps, features, edition, version
├── Cargo.lock          # locked dep versions (commit for bins; not for libs)
├── src/
│   └── main.rs         # binary entry point
│       OR
│   └── lib.rs          # library entry point
└── tests/              # integration tests (optional)
```

For libraries: add `lib.rs`. For binaries: `main.rs`. Workspaces (multi-crate) are common in real projects — agent sets up `[workspace]` in the top-level `Cargo.toml`.

---

## Cargo.toml

The manifest — deps, features, edition, version. What to check in agent output:

```toml
[package]
name = "mynewproduct"
version = "0.0.0"          # release tooling owns this — don't hand-bump
edition = "2024"
license = "MIT"

[dependencies]
# added via `cargo add`, not hand-edited
```

- **`edition = "2024"`** — current edition. `2021` is fine on older crates; `2018`/`2015` in new code is a smell.
- **Workspaces**: multi-crate repos put `[workspace]` in the top-level `Cargo.toml`. Member crates share deps via `[workspace.dependencies]` + `dep = { workspace = true }`; version/edition/license set once under `[workspace.package]`.
- **`Cargo.lock`**: committed for binaries and workspaces, not for standalone libraries.
- **Version**: don't hand-edit. `putitoutthere` bumps it per the `release:` trailer (see [shipping.md](shipping.md)).
- **Deps added with `cargo add`** — a hand-edited `[dependencies]` block with no `cargo add` in the diff is worth a glance for typo'd or pinned-too-loose versions.

---

## Ecosystem cheat sheet

Common crates an agent should reach for. If they pick something off-brand for a standard task, ask why.

| Task | De facto crate |
|---|---|
| CLI args | `clap` |
| Serialization | `serde` + `serde_json` / `serde_yaml` / `bincode` |
| Async runtime | `tokio` |
| Error handling (binary) | `anyhow` |
| Error definition (library) | `thiserror` |
| HTTP client | `reqwest` |
| Web framework | `axum` (modern) or `actix-web` (more mature) |
| Database (async) | `sqlx` |
| Database (sync, ORM) | `diesel` |
| Structured logging | `tracing` |
| Data parallelism | `rayon` |
| Python bindings | `pyo3` |
| Node/JS bindings | `napi-rs` |
