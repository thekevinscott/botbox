# Rust — review

The full smell catalog is in [code-smells.md](code-smells.md) — load it for review, not for generation.

## Pre-review tooling pass

Before any line-by-line read, run these. They mechanically eliminate most smells:

```fish
cargo check         # does it compile?
cargo clippy        # is it idiomatic?
cargo test          # do tests pass?
cargo fmt --check   # is it formatted?
```

If the agent didn't run these, ask it to. If they fail, the agent should fix before you spend reviewer time.

## Reading-a-PR checklist

1. **Tooling pass** — all four green?
2. **`.unwrap()` / `.expect()` / `unsafe`** — scan for these, pause on each.
3. **Function signatures** — `&T` where appropriate, or unnecessarily `T`?
4. **Error context** — every `?` chain has `.with_context(...)` somewhere upstream?
5. **Tests** — inline `#[cfg(test)] mod tests`? Cover the public surface?
6. **`Cargo.toml` changes** — new crates reputable (see ecosystem table in [setup.md](setup.md))?
7. **Reinvention** — did the agent rebuild something a standard crate provides?
8. **Naming** — `new`/`with_*`/`from`/`try_*` for constructors?
9. **Public API** — `pub` surface intentional (not over-exposed); typed `thiserror` errors in libraries; `#[non_exhaustive]` where the type will grow.
10. **Changelog fragment** — a `docs/changelog.d/` fragment added (plus `docs/migrations.d/` when breaking) for any consumer-observable change, or a `skip-changelog:` trailer present (philosophy in [../repo.md](../repo.md)).
11. **`putitoutthere.toml`** — `globs` cover every source path that should cascade a release; polyglot CLIs declare `depends_on` correctly.

---

## Compiler error vocabulary

- "*expected `X`, found `Y`*" — type mismatch. Often a missing `&`, missing `.to_string()`, etc.
- "*no method named `foo` found*" — usually means a trait isn't in scope. Add the `use` for the trait.
- "*cannot borrow `x` as mutable, as it is not declared as mutable*" — add `mut` to the `let`.
- "*value moved here, but borrow occurs later*" — you consumed when you should have borrowed.
- "*does not live long enough*" — a borrow outlives the owner. Restructure or own.
- "*cannot move out of borrowed content*" — you tried to consume something you only have a borrow to.
