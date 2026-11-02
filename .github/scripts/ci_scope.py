"""Print `scope=` and `gates=` for the files a PR changes, for $GITHUB_OUTPUT.

A PR that changes only one kind of test gets that scope, and workflows skip every job outside it.
Anything else, or a mix, is `full`. Docs never narrow or widen the scope.

Usage: ci_scope.py BASE HEAD
"""

import re
import subprocess
import sys

KINDS = {
    "e2e": re.compile(r"packages/python/(tests/e2e|e2e-attestations)/"),
    "integration": re.compile(r"packages/python/tests/integration/"),
    "unit": re.compile(r"packages/python/src/.*_test\.py$"),
}

# testing-conventions gates per scope. Unit tests sit in src/, so they need a fresh e2e receipt.
GATES = {
    "e2e": '["e2e-verify"]',
    "integration": '["integration-lint"]',
    "unit": '["colocated-test", "one-function-per-file", "unit-lint", "unit-coverage", "mutation", "e2e-verify"]',
    "full": "",
}


def kind(path: str) -> str | None:
    if path.startswith("docs/"):
        return None
    return next((name for name, pattern in KINDS.items() if pattern.match(path)), "full")


def scope(paths: list[str]) -> str:
    kinds = {kind(path) for path in paths} - {None}
    return kinds.pop() if len(kinds) == 1 else "full"


def main() -> None:
    base, head = sys.argv[1:]
    diff = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        check=True,
    )
    narrowed = scope(diff.stdout.split())
    print(f"scope={narrowed}")
    print(f"gates={GATES[narrowed]}")


if __name__ == "__main__":
    main()
