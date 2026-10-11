# Python — setup

- Python 3.12+
- uv

Python floor pinned in `pyproject.toml`:

```toml
[project]
requires-python = ">=3.12"
```

## Common Libraries

- pytest + pytest-describe + pytest-asyncio for testing
- ruff for lint + format
- ty (or mypy / pyright) for type checking
- hatchling + hatch-vcs for pure-Python build
- maturin for PyO3-Rust build
- just for task running
- bandit for security scanning

**Package management is `uv`.** The `uv add` / `uv sync` / `uv run` triad covers install, lock, and run — `uv run` invokes commands inside the project venv against the lockfile, no manual `source .venv/bin/activate` needed. Never `pip` — not `uv pip` (a compatibility shim), not `python -m pip` — it bypasses the lockfile.

## Watch mode

```fish
uv run pytest-watcher .
```

There's no monolithic watcher like Rust's `bacon`; compose your own from `pytest-watcher` (asyncio-aware) and a parallel `ty --watch` if you want type-check feedback in another pane.

---

## Project shape

Flat layout:

```
mynewproduct/
  mynewproduct/
    __init__.py
    core.py
    core_test.py             # colocated unit test
    cli/
      __init__.py
      main.py
  tests/
    conftest.py
    integration/             # cross-module, mock third-party deps
    e2e/                     # CLI invocation, no mocking, not run by CI
  docs/
  scripts/
  pyproject.toml
  uv.lock
  justfile
  putitoutthere.toml
  README.md
  CHANGELOG.md             # pointer stub — the record is docs/changelog.d/ (see ../repo.md)
  MIGRATIONS.md            # pointer stub — the record is docs/migrations.d/
  LICENSE
```

For PyO3 / maturin packages: Rust source in `src/`, Python source in `python/` (or wherever `tool.maturin.python-source` points), tests in `tests/`:

```
mynewproduct/
  src/                       # Rust (PyO3) source
    lib.rs
  python/
    mynewproduct/
      __init__.py            # re-exports from compiled _mynewproduct
  tests/
  pyproject.toml             # build-backend = "maturin"
```

`__init__.py` should be **the thinnest possible** public-API surface. Re-export named items, set `__all__`, don't import heavy deps eagerly:

```python
"""mynewproduct - one-line description."""

from importlib.metadata import version

from mynewproduct.errors import MyNewProductError, ValidationError, NotFoundError

__version__ = version("mynewproduct")

__all__ = ["MyNewProductError", "ValidationError", "NotFoundError", "__version__"]
```

For libraries that ship optional heavy subsystems (numpy, torch, etc.), use **PEP 562 lazy imports** to keep `import mynewproduct` cheap:

```python
# mynewproduct/__init__.py
_LAZY: dict[str, str] = {
    "evaluate": "mynewproduct.eval",
    "tune": "mynewproduct.tune",
}

def __getattr__(name: str):
    if name in _LAZY:
        import importlib
        module = importlib.import_module(_LAZY[name])
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

**One-public-callable-per-file**: each `.py` exports a single function/class named to match the filename (`get_rate_color.py` → `get_rate_color()`). Multi-callable files get promoted to subpackages with one file per callable. Exempt: `types.py`, `models.py`, `errors.py`, `__init__.py`, `conftest.py`, `dataclasses.py`.

---

## pyproject.toml

```toml
[build-system]
requires = ["hatchling>=1.20", "hatch-vcs>=0.4"]
build-backend = "hatchling.build"

[project]
name = "mynewproduct"
dynamic = ["version"]
description = "One-line description."
readme = "README.md"
requires-python = ">=3.12"
license = "MIT"
authors = [{ name = "Author", email = "author@example.com" }]
keywords = ["..."]
classifiers = [
  "Development Status :: 4 - Beta",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "License :: OSI Approved :: MIT License",
]
dependencies = [
  "pyyaml>=6.0",
  "rich>=13.0",
]

[project.optional-dependencies]
dev = [
  "ruff>=0.8",
  "pytest>=8.0",
  "pytest-asyncio>=0.24",
  "pytest-describe>=2.0",
  "pytest-cov>=4.0",
  "pytest-watcher>=0.4",
  "ty>=0.0.1a7",          # or "mypy>=1.10"
  "bandit>=1.7",
]

[project.scripts]
mynewproduct = "mynewproduct.cli.main:main"

[project.urls]
Homepage = "https://github.com/org/mynewproduct"
Documentation = "https://mynewproduct.dev"
Issues = "https://github.com/org/mynewproduct/issues"

[tool.hatch.version]
source = "vcs"

[tool.hatch.build.targets.wheel]
packages = ["mynewproduct"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "C90", "UP", "ARG", "SIM", "PTH", "PLR", "RUF"]
ignore = []

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.ruff.lint.pylint]
max-args = 8
max-statements = 50

[tool.ruff.lint.per-file-ignores]
"*_test.py" = ["PLR2004", "PLR0915", "C901"]
"tests/**/*.py" = ["PLR2004", "PLR0915", "C901"]

[tool.ruff.lint.isort]
known-first-party = ["mynewproduct"]

[tool.ruff.format]
quote-style = "double"

[tool.pytest.ini_options]
testpaths = ["mynewproduct", "tests"]
python_files = ["*_test.py", "test_*.py"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"

[tool.coverage.run]
branch = true
source = ["mynewproduct"]
omit = ["*_test.py", "tests/*"]

[tool.coverage.report]
fail_under = 85
exclude_lines = [
  "pragma: no cover",
  "raise NotImplementedError",
  "if TYPE_CHECKING:",
]

[tool.bandit]
skips = ["B101"]            # assert_used — fine in tests
```

Things worth getting right:

- **Build backend**: `hatchling` for pure-Python, `maturin` for PyO3.
- **Dynamic version from VCS tags** (`hatch-vcs`). No hardcoded version, no `__version__ = "0.1.0"` to update. Wheel version comes from `git describe`.
- **`requires-python = ">=3.12"`** — lets you use PEP 695 generics (`def f[T](x: T) -> T:`) and `int | None` everywhere without `from __future__ import annotations`.
- **`[project.scripts]`** for CLI entry points — not `console_scripts` (legacy).
- **`[project.urls]`** populated. PyPI shows these on the project page.
- **`asyncio_mode = "auto"`** — every test is async-aware automatically. Drops the `@pytest.mark.asyncio` boilerplate.

**uv stays implicit via `uv.lock`** — add a `[tool.uv]` block only when you need to override its defaults.

---

## Configuration

**Minimal.** A library should take a config object (or kwargs) at instantiation. Settings systems (`pydantic-settings`, `dynaconf`) belong in apps, not libraries.

For application-level config, the minimum:

```python
# mynewproduct/config.py
import os
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("MYNEWPRODUCT_DIR", str(Path.home() / ".mynewproduct")))
CACHE_DIR = PROJECT_DIR / "cache"
```

If you reach for `pydantic-settings`, you're past minimum. That's fine — verify the project needs typed env-var loading with validation, not just `os.environ.get`.

**Ship `.env.example` and `.gitignore` the real `.env`.** Document the variables the example carries; the real `.env` stays out of the repo.

---

## Ecosystem cheat sheet

| Task | De facto choice |
|---|---|
| Package manager | `uv` |
| Build (pure Python) | `hatchling` (+ `hatch-vcs`) |
| Build (PyO3 native) | `maturin` |
| Test runner | `pytest` |
| Test grouping | `pytest-describe` |
| Async tests | `pytest-asyncio` (`asyncio_mode = "auto"`) |
| Type checker | `mypy` (mature) / `pyright` / `ty` (alpha) |
| Linter + formatter | `ruff` |
| Security | `bandit` |
| CLI (production tool) | Rust crate with `clap`, Python wrapper via `maturin` + `bundle_cli` |
| CLI args (pure-Python utility) | `cyclopts` / `click` / `typer` |
| HTTP client (sync) | `httpx` (or `requests` if legacy) |
| HTTP client (async) | `httpx.AsyncClient` / `aiohttp` |
| Schema validation | `pydantic` (v2) |
| Settings | `pydantic-settings` (apps only) |
| Date/time | `whenever` (modern) / stdlib `datetime` |
| Logging | `structlog` / stdlib `logging` |
| Concurrency primitives | stdlib `asyncio` / `concurrent.futures` |
| Plotting | `matplotlib` (slow defaults) / `plotly` (interactive) |
| Numerics | `numpy`, `polars` (preferred over pandas for new projects) |
| Docs | `mkdocs` + `mkdocs-material` + `mkdocstrings` |
| Versioning (in-package) | `hatch-vcs` (VCS-derived) |
| Release orchestration | `putitoutthere` (reusable workflow + `putitoutthere.toml`) |
| Pre-commit | `pre-commit` framework — but prefer pre-push |
