---
diataxis: how-to
---

# Testing conventions

> **Why read this:** every PR is gated on this rule — learn what it asks for
> (a colocated unit test per source file) and how to pass the check locally
> before CI runs it.

This repo follows the [testing-conventions](https://github.com/thekevinscott/testing-conventions)
standard and enforces it in CI.

## The rule

Every source file has a **colocated** unit test named after it:

| Language   | Source        | Colocated test     |
| ---------- | ------------- | ------------------ |
| Python     | `foo.py`      | `foo_test.py`      |
| TypeScript | `foo.ts`      | `foo.test.ts`      |
| Rust       | `foo.rs`      | inline `#[cfg(test)] mod tests` |

Move the source, the test moves with it. (Python's `__init__.py` and TypeScript
declaration files `*.d.ts` are exempt; Rust uses inline tests, so the
colocated-file rule does not apply to it.)

## How it's enforced

`.github/workflows/conventions.yml` calls the upstream reusable workflow on every
pull request. It installs the published `testing-conventions` binary from
crates.io and runs the location check per language, failing the build — with the
offending files in the log — on any source file missing its colocated test.

Run the same check locally:

```sh
cargo install testing-conventions
testing-conventions unit location --language typescript packages/node/src
testing-conventions unit location --language python packages/python
```
