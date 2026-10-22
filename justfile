set shell := ["bash", "-cu"]

default:
    @just --list

# ---- Python --------------------------------------------------------------
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

# .env lives in the main checkout; worktrees share its git common dir.
test-e2e:
    cd packages/python && uv run --env-file "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/.env" pytest tests/e2e

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
