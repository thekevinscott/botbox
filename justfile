set shell := ["bash", "-cu"]

default:
    @just --list

# ---- Python --------------------------------------------------------------
lint:
    cd packages/python && uv run ruff check . && uv run ruff format --check .

format:
    cd packages/python && uv run ruff check --fix . && uv run ruff format .

# Separate runs: tests/ resolves sibling imports (conftest, fake_docker_test) as top-level modules.
typecheck:
    cd packages/python && uv run mypy src
    cd packages/python && uv run mypy tests/integration
    cd packages/python && uv run mypy tests/e2e

test-unit:
    cd packages/python && uv run pytest src

test-integration:
    cd packages/python && uv run pytest tests/integration

test-e2e:
    cd packages/python && uv run --env-file ../../.env pytest tests/e2e

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

# ---- Aggregates ----------------------------------------------------------

test: test-unit test-integration

ci: lint gha-lint typecheck test

hooks:
    pre-commit install --install-hooks

clean:
    rm -rf packages/python/dist docs/.vitepress/dist
