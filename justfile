set shell := ["bash", "-cu"]

default:
    @just --list

# ---- Python --------------------------------------------------------------
# pytest exit 5 means no tests collected: the e2e lane exists before its tests do.

lint:
    cd packages/python && uv run ruff check . && uv run ruff format --check .

format:
    cd packages/python && uv run ruff check --fix . && uv run ruff format .

typecheck:
    cd packages/python && uv run mypy src

test-unit:
    cd packages/python && uv run pytest src

test-integration:
    cd packages/python && uv run pytest tests/integration

test-e2e:
    cd packages/python && { uv run pytest tests/e2e || [ $? -eq 5 ]; }

build:
    cd packages/python && uv build

# ---- Docs ----------------------------------------------------------------

docs-install:
    cd docs && pnpm install --no-frozen-lockfile

docs-dev:
    cd docs && pnpm run dev

docs-build:
    cd docs && pnpm run build

# ---- CI gates (repo-internal `ci` package) --------------------------------

# Gate: fail if any workflow / composite-action YAML encodes a non-trivial
# inline script (docs/internals/repo.md). Run from the repo root.
gha-lint:
    npx --yes testing-conventions workflow-lint

gha-test:
    cd ci && uv run pytest

# ---- Aggregates ----------------------------------------------------------

test: test-unit test-integration gha-test

ci: lint gha-lint typecheck test

hooks:
    pre-commit install --install-hooks

clean:
    rm -rf packages/python/dist docs/.vitepress/dist
