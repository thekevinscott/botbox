set shell := ["bash", "-cu"]

default:
    @just --list

# ---- Rust ----------------------------------------------------------------

rust-lint:
    cd packages/rust && cargo fmt --all -- --check && cargo clippy --all-targets -- -D warnings

rust-format:
    cd packages/rust && cargo fmt --all

rust-test:
    cd packages/rust && cargo test

rust-cov:
    cd packages/rust && cargo llvm-cov --ignore-filename-regex 'main\.rs' --fail-under-lines 95

rust-build:
    cd packages/rust && cargo build --release

# ---- Python --------------------------------------------------------------

py-lint:
    cd packages/python && ruff check . && ruff format --check .

py-format:
    cd packages/python && ruff check --fix . && ruff format .

py-typecheck:
    cd packages/python && mypy .

py-test:
    cd packages/python && pytest

py-build:
    cd packages/python && maturin build --release

# ---- Node ----------------------------------------------------------------

node-install:
    cd packages/node && pnpm install --no-frozen-lockfile

node-lint:
    cd packages/node && pnpm run lint

node-typecheck:
    cd packages/node && pnpm run typecheck

node-test:
    cd packages/node && pnpm run test

node-build:
    cd packages/node && pnpm run build

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

lint: rust-lint py-lint node-lint gha-lint
format: rust-format py-format
typecheck: py-typecheck node-typecheck
test: rust-test py-test node-test gha-test
build: rust-build py-build node-build

ci: lint typecheck test

hooks:
    pre-commit install --install-hooks

clean:
    rm -rf packages/rust/target packages/python/dist packages/node/dist docs/.vitepress/dist
