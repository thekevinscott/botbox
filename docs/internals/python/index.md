# Python — agent-supervision guide

uv-managed venv, `hatchling` (or `maturin`) build backend, native 3.12+ syntax, type-checked in CI, `ruff` for lint and format, `pytest` with `pytest-describe`, `putitoutthere` for releases.

## Sub-docs

- [setup.md](setup.md) — toolchain, common libraries, watch mode, project shape, `pyproject.toml`, configuration, ecosystem cheat sheet
- [style.md](style.md) — type hints, async / sync discipline, what good Python code looks like
- [testing.md](testing.md) — pytest, pytest-describe, fixtures, coverage
- [shipping.md](shipping.md) — Github, public API design, CLI, lint + format, repo orchestration, CI/CD, release flow, PyO3 bindings
- [review.md](review.md) — pre-review tooling pass, reading-a-PR checklist, common type errors

Cross-cutting repo conventions (changelog/migration fragment philosophy) live in [../repo.md](../repo.md).

## One-paragraph summary

uv-managed venv, `hatchling` (or `maturin`) build backend, dynamic version from VCS tags, `requires-python = ">=3.12"`, native 3.12+ syntax with PEP 695 generics and `T | None`, type-check with mypy/pyright/ty in CI, ruff for lint and format with a focused rule set, pytest with `pytest-describe` and `asyncio_mode = "auto"`, dataclasses for internal data and Pydantic at boundaries, single flat exception hierarchy, lazy `__init__.py` for libraries with heavy optional deps, `putitoutthere` for cross-registry releases driven by `putitoutthere.toml` and a seven-line reusable workflow, a changelog fragment under `docs/changelog.d/` on every consumer-observable change, mkdocs-material + mkdocstrings for docs, justfile for contributor commands with parallel lint/format/typecheck. CLIs ship as a Rust crate with TS and Python wrappers — `clap` parses, the crate runs, `bundle_cli` stages a per-platform binary into each wheel so `pip install` lands a working command on `PATH`. The qualities to reinforce are typed public surfaces, specific exception handling, non-blocking async, and reuse of stdlib facilities (paths via `pathlib`, retry via `tenacity`, schema via `pydantic`).
