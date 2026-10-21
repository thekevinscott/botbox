# Testing conventions

> **Why read this:** every PR is gated on this rule — learn what it asks for (a colocated unit test per source file) and how to pass the check locally before CI runs it.

This repo follows the [testing-conventions](https://github.com/thekevinscott/testing-conventions) standard and enforces it in CI.

## The rule

Every source file has a **colocated** unit test named after it:

| Language   | Source        | Colocated test     |
| ---------- | ------------- | ------------------ |
| Python     | `foo.py`      | `foo_test.py`      |

Move the source, the test moves with it. (`__init__.py` is exempt.)

## How it's enforced

`.github/workflows/conventions.yml` calls the upstream reusable workflow on every pull request. It installs the published `testing-conventions` binary from crates.io and runs the location check, failing the build — with the offending files in the log — on any source file missing its colocated test.

Run the same check locally:

```sh
cargo install testing-conventions
testing-conventions unit location --language python packages/python
```

Next: [Guides](./).
