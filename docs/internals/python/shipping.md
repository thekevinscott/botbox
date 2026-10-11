# Python — shipping

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

**Docstrings**: short, *why*-oriented. Let the signature carry the structure:

```python
def parse(content: str, *, strict: bool = False) -> Document:
    """Parse a document, raising on the first ambiguity if strict.

    The non-strict mode is forgiving for back-compat; new callers should set
    strict=True to surface schema drift early.
    """
```

When the type hints carry the structure, the prose carries the rationale.

**API reference via `mkdocs-material` + `mkdocstrings`** for new projects; `sphinx` + `sphinx-autodoc` is the mature alternative. Both render docstrings to HTML.

**Exception hierarchy** — define a flat tree at `mynewproduct/errors.py`, re-export from `__init__.py`:

```python
# mynewproduct/errors.py
class MyNewProductError(Exception):
    """Base exception for mynewproduct."""

class ValidationError(MyNewProductError):
    """A user input failed schema validation."""

class NotFoundError(MyNewProductError):
    """The requested resource does not exist."""
```

```python
# mynewproduct/__init__.py
from mynewproduct.errors import MyNewProductError, ValidationError, NotFoundError
__all__ = ["MyNewProductError", "ValidationError", "NotFoundError", "__version__"]
```

Give each failure mode its own exception variant. One variant per condition (lock-poison, init-failure, not-ready) keeps `except` clauses precise.

**Class-with-`__call__` vs function**: prefer a function for one-shot behaviour; a class for stateful workflows. Intermediate variables read better in Python than chained pipelines (`process(data).then(...).then(...)`).

**Avoid built-in names for fields and variables** (`type`, `id`, `list`, `dict`, `input`, `format`). Use `kind`/`type_` and `key`/`id_` so the built-in stays usable in scope.

---

## CLI

**Every CLI is a Rust binary.** The Python package is a thin wrapper that puts the binary on `PATH` through `pip install`. Argument parsing (clap), validation, exit codes, the whole runtime lives in the crate. Same goes for the npm sibling.

Why: one source of truth for argument grammar, help text, and error messages across `pip install` and `npm install -g`. `clap` is the strongest CLI framework available, cross-platform static binaries solve distribution, and the wrapper layer stays minimal.

### Layout

```
mynewproduct/
  packages/
    rust/              # binary crate — Cargo.toml, src/main.rs (clap App)
      Cargo.toml
      src/
    node/              # npm wrapper sibling (see ../typescript/shipping.md)
    python/            # this package
      pyproject.toml
      src/mynewproduct/
        __init__.py
        _binary/
          __init__.py  # entrypoint — execs the staged binary
  putitoutthere.toml
  CHANGELOG.md       # pointer stub — the record is docs/changelog.d/
  MIGRATIONS.md      # pointer stub — the record is docs/migrations.d/
  LICENSE
```

### `pyproject.toml`

```toml
[build-system]
requires = ["maturin>=1.5"]
build-backend = "maturin"

[project]
name = "mynewproduct"
dynamic = ["version"]
requires-python = ">=3.12"

[project.scripts]
mynewproduct = "mynewproduct._binary:entrypoint"

[tool.maturin]
python-source = "src"
include = ["src/mynewproduct/_binary/**"]
```

### Launcher

`src/mynewproduct/_binary/__init__.py`:

```python
import os
import sys
from pathlib import Path


def entrypoint() -> None:
    here = Path(__file__).parent
    binary = here / ("mynewproduct.exe" if os.name == "nt" else "mynewproduct")
    if not binary.exists():
        sys.stderr.write(f"mynewproduct binary not found at {binary}\n")
        sys.exit(1)
    os.execv(binary, [str(binary), *sys.argv[1:]])
```

`os.execv` replaces the Python process — no orphaned interpreter, signals route directly to the binary.

### `putitoutthere.toml`

Three-artifact shape:

```toml
[putitoutthere]
version = 1

[[package]]
name          = "mynewproduct-rust"
kind          = "crates"
crate         = "mynewproduct"
path          = "packages/rust"
first_version = "0.0.1"
globs         = ["packages/rust/**", "LICENSE"]

[[package]]
name          = "mynewproduct-py"
kind          = "pypi"
pypi          = "mynewproduct"
path          = "packages/python"
first_version = "0.0.1"
build         = "maturin"
depends_on    = ["mynewproduct-rust"]
globs         = ["packages/python/**", "packages/rust/**", "LICENSE"]
targets = [
  "x86_64-unknown-linux-gnu",
  "aarch64-unknown-linux-gnu",
  "x86_64-apple-darwin",
  "aarch64-apple-darwin",
  "x86_64-pc-windows-msvc",
]
# (npm sibling package omitted — see ../typescript/shipping.md)
```

`putitoutthere` cross-compiles the binary per target, stages it into `src/mynewproduct/_binary/` before maturin runs, and ships one wheel per platform. `pip install mynewproduct` on any platform gets a working CLI on PATH with no Rust toolchain required.

### Testing

The crate's logic is tested in Rust (`cargo test`). The Python wrapper ships a single happy-path e2e per command — drive the actual binary in a subprocess and assert against output:

```python
import subprocess

def it_runs_the_tool(tmp_path):
    result = subprocess.run(
        ["mynewproduct", "run", "--input", str(tmp_path / "in.json")],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "done" in result.stdout
```

### Pure-Python utilities

For a small Python-only utility that isn't worth a Rust core (script, internal tool, ad-hoc batch job): `cyclopts` for type-driven multi-command CLIs, `click`/`typer` as mature alternatives, `argparse` for one-shot scripts. Anything that's going to be installed by more than a handful of people gets the Rust shape.

---

## Lint + format

**`ruff` for both.** One tool handles formatting, import sorting, and lint, faster than the legacy three-tool pipeline.

```toml
[tool.ruff]
line-length = 100        # 100 is reasonable; 88 (black default) is defensible
target-version = "py312"

[tool.ruff.lint]
select = [
  "E",    # pycodestyle errors
  "W",    # pycodestyle warnings
  "F",    # pyflakes
  "I",    # isort (import sorting)
  "B",    # flake8-bugbear (likely bugs)
  "C4",   # flake8-comprehensions
  "C90",  # mccabe complexity
  "UP",   # pyupgrade (modernise syntax)
  "ARG",  # unused-argument
  "SIM",  # flake8-simplify
  "PTH",  # use pathlib
  "PLR",  # pylint refactor (incl. complexity)
  "RUF",  # ruff-specific
]
```

Enable rule groups deliberately. The set above is a reasonable starting point. `D` (pydocstyle) is rarely worth the friction it adds.

**Per-file ignores for tests** (`PLR2004` magic numbers, `PLR0915` too-many-statements, `C901` too-complex are all OK in tests):

```toml
[tool.ruff.lint.per-file-ignores]
"*_test.py" = ["PLR2004", "PLR0915", "C901"]
"tests/**/*.py" = ["PLR2004", "PLR0915", "C901"]
```

**Type checker in CI** — `ty check mynewproduct/` or `mypy mynewproduct/` as a separate job. Type errors block merge.

**Security**: `bandit` is fine to run in CI. Tell it to skip `B101` (assert-used) for tests. Scope the per-file `# nosec B603,B607` annotations rather than blanket-skipping subprocess rules globally.

**`docformatter`**: optional. If you maintain Google-style docstrings, it formats them; if not, skip.

---

## Repo orchestration

**`justfile`** for contributor commands.

```make
default: ci

lint:
    uv run ruff check .

format:
    uv run ruff format .

format-check:
    uv run ruff format --check .

typecheck:
    uv run ty check mynewproduct/

test-unit:
    uv run pytest mynewproduct/ -x -q

test-integration:
    uv run pytest tests/integration/ -x -q

test-e2e:
    uv run pytest tests/e2e/ -x -q

test-cov:
    uv run pytest --cov=mynewproduct --cov-report=term-missing --cov-fail-under=85

ci:
    #!/usr/bin/env bash
    set -euo pipefail
    just lint &
    just format-check &
    just typecheck &
    wait
    just test-unit
    just test-cov

clean:
    rm -rf dist/ build/ .pytest_cache/ .ruff_cache/ .coverage htmlcov/

build:
    uv build
```

Run lint/format-check/typecheck in parallel before tests. Meaningful speedup.

**Pre-push (not pre-commit)** if you want client-side enforcement. Pre-commit hooks on every commit are net-negative — they slow down WIP commits and people learn to `--no-verify`. Pre-push runs once before the push, after you've reorganised commits. Install via `just hooks`:

```fish
#!/bin/sh
# scripts/hooks/pre-push
just ci
```

---

## CI/CD

`.github/workflows/` layout:

| File | Purpose |
|---|---|
| `test.yml` | `uv run pytest` matrix on Python 3.12, 3.13 |
| `lint.yml` | `uv run ruff check` + `ruff format --check` |
| `typecheck.yml` | `uv run ty check` (or mypy) |
| `security.yml` | `bandit -r mynewproduct` |
| `coverage.yml` | `pytest --cov --cov-fail-under=85` |
| `docs.yml` | Build + deploy mkdocs/sphinx site |
| `changelog-check.yml` | changelog fragment added under `docs/changelog.d/` (or `skip-changelog:` trailer) |
| `release.yml` | `uses: thekevinscott/putitoutthere/.github/workflows/release.yml@v0` |

**Use `astral-sh/setup-uv@v7`**, not `actions/setup-python`. uv installs and pins Python itself:

```yaml
- uses: actions/checkout@v6
- uses: astral-sh/setup-uv@v7
  with:
    python-version: "3.12"
    enable-cache: true
- run: uv sync --frozen
- run: uv run pytest
```

**Path filters** on every workflow so docs-only PRs don't run the test matrix:

```yaml
on:
  push:
    paths:
      - "mynewproduct/**"
      - "tests/**"
      - "pyproject.toml"
      - "uv.lock"
      - ".github/workflows/test.yml"
```

**Matrix sparingly.** Python 3.12 + 3.13 is enough; cross-OS only if you have native code or filesystem-specific behaviour. For PyO3 packages, matrix OS for wheel builds, Ubuntu-only for tests.

**Concurrency cancel previous runs**:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

---

## Release flow

**Use `putitoutthere`.** Single reusable workflow, single config file, OIDC trusted publishers across PyPI / crates.io / npm. Versions derive from git tags via `hatch-vcs`. Provenance, retry-with-backoff, tag rollback, registry idempotency are all inside the workflow. Cross-cutting CHANGELOG / MIGRATIONS rules live in [../repo.md](../repo.md).

### Version source

putitoutthere never edits `pyproject.toml`, so the build backend must derive the release version itself. Three shapes reach it:

| Backend | Version source | How the release version arrives |
| --- | --- | --- |
| hatch-vcs | `[tool.hatch.version] source = "vcs"` | `SETUPTOOLS_SCM_PRETEND_VERSION` |
| setuptools-scm | `[tool.setuptools_scm]` | `SETUPTOOLS_SCM_PRETEND_VERSION` |
| maturin | sibling `Cargo.toml` | putitoutthere rewrites the manifest pre-build |

**The fourth shape is a trap.** Plain hatchling with `[tool.hatch.version] path = "src/pkg/_version.py"` passes putitoutthere's PR-time check (`dynamic = ["version"]` plus a `[tool.hatch.version]` block), but nothing rewrites that literal and hatchling ignores `SETUPTOOLS_SCM_PRETEND_VERSION`. The wheel silently ships whatever is on disk. A fork that prunes Rust loses maturin's version source and must switch to hatch-vcs, not this.

**Runtime `__version__` reads installed metadata**, never a literal: `__version__ = importlib.metadata.version("mynewproduct")`. A literal is the same bug one layer up.

### `putitoutthere.toml`

Repo-root config. Prescriptive schema — every package declares the same fields; defaults stay implicit.

```toml
[putitoutthere]
version = 1

[[package]]
name       = "mynewproduct"
kind       = "pypi"
path       = "."
globs      = ["mynewproduct/**/*.py", "pyproject.toml", "uv.lock"]
build      = "hatch"            # or "maturin" for PyO3 packages
tag_format = "v{version}"
```

For maturin packages, declare `targets`:

```toml
[[package]]
name    = "mynewproduct"
kind    = "pypi"
path    = "."
globs   = ["src/**", "python/**", "pyproject.toml"]
build   = "maturin"
targets = [
  "x86_64-unknown-linux-gnu",
  "aarch64-unknown-linux-gnu",
  "x86_64-apple-darwin",
  "aarch64-apple-darwin",
  "x86_64-pc-windows-msvc",
]
```

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

The workflow drives `plan → build → publish → GitHub Release`. Consumer-side YAML stays at the seven-line stub above. `SETUPTOOLS_SCM_PRETEND_VERSION` handoff for `hatch-vcs` dynamic-version builds is set inside the workflow.

### Release trailer

Default cascade bump is `patch`. Override in the merge-commit body:

```
fix: handle empty token lists

release: minor
```

Grammar: `release: {patch|minor|major|skip} [pkg1, pkg2, ...]`. Last trailer wins. Optional package list scopes the bump.

### Trusted publishers

One-time registry setup per package — OIDC only.

- **PyPI**: under `https://pypi.org/manage/project/<name>/settings/publishing/`, add the GitHub publisher (owner, repo, workflow filename, and — if you pin one — the `release` environment). Brand-new projects use a pending publisher.
- **crates.io** (when the package ships a Rust core): publish once via classic `cargo`, then enable trusted publishing under `https://crates.io/crates/<crate>/settings`.
- **npm** (when the package has a TS wrapper sibling): bootstrap one version with `NODE_AUTH_TOKEN`, then **Require trusted publisher** under `https://www.npmjs.com/package/<name>/access`.

---

## PyO3 bindings

When the Python package wraps a Rust crate via PyO3 + maturin:

- **The binding wraps the Rust *SDK***, not the core directly. If you find yourself reimplementing scanner-loops, watcher-loops, or domain logic in the PyO3 binding, you've drifted — that work belongs in the SDK crate, which both bindings (Python, JS) consume.
- **`extension-module` feature** in `Cargo.toml`, gated by `[features]` so the crate can also build as a plain rlib for testing:

  ```toml
  [features]
  extension-module = ["pyo3/extension-module"]
  [dependencies]
  pyo3 = { version = "0.22", default-features = false, features = ["macros"] }
  ```

- **`module-name = "mynewproduct._mycore"`** with the `_`-prefix convention. The Python package re-exports from the compiled extension.
- **Preserve type info across the FFI boundary** — convert Rust types to Python types deliberately:

  ```rust
  fn convert_value(py: Python, v: &Value) -> PyResult<PyObject> {
      // bool BEFORE int — Python's bool is a subclass of int
      match v {
          Value::Bool(b) => Ok(b.into_py(py)),
          Value::Int(i) => Ok(i.into_py(py)),
          Value::String(s) => Ok(s.into_py(py)),
          // ...
      }
  }
  ```

  The `bool`-before-`int` ordering matters for Python's subtype rules.

- **Map Rust error variants to specific Python exception types** at the boundary, so Python consumers can `except` precisely:

  ```rust
  match err {
      DbError::SchemaMismatch(msg) => SchemaMismatchError::new_err(msg),
      DbError::NotFound(name) => NotFoundError::new_err(format!("not found: {name}")),
      _ => PyRuntimeError::new_err(err.to_string()),
  }
  ```

  Stringifying every error means Python consumers see a generic `RuntimeError` and can't catch specifics.

- **Ship typed stubs** if the public API is non-trivial. Either inline `.pyi` files or maturin-generated stubs.
- **`py.typed` marker** in the Python source dir so type checkers know the package is typed.
