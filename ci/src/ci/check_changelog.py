"""Enforce that package changes add a changelog fragment.

Lives in the repo-internal ``ci`` CLI (``ci check-changelog``) so the
package-detection logic is unit-testable instead of frozen in inline shell.
``.github/workflows/changelog.yml`` invokes it as a one-line ``run:`` step,
passing the PR's base/head SHAs via env.

A PR whose non-test, non-stub source changed under ``packages/<pkg>/`` must
add at least one fragment naming that package under ``docs/changelog.d/`` or
``docs/migrations.d/`` — one timestamped file per PR, named
``YYYY-MM-DD-<pkg>-<slug>.md`` (UTC merge date). Any file touched in those
folders is validated against that pattern (``README.md``, each folder's
index, is the one exception). Bypass by adding a ``skip-changelog:`` trailer
to any commit on the PR.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess

_SKIP_TRAILER = re.compile(r"^skip-changelog:", re.IGNORECASE | re.MULTILINE)
_FRAGMENT_DIRS = ("docs/changelog.d", "docs/migrations.d")
_FRAGMENT_NAME = re.compile(r"\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md")


def has_skip_trailer(commit_messages: str) -> bool:
    """True if any commit body line starts with ``skip-changelog:``."""
    return bool(_SKIP_TRAILER.search(commit_messages))


def changed_packages(changed: list[str]) -> list[str]:
    """Unique, sorted package names touched under ``packages/<name>/...``."""
    pkgs = {
        parts[1]
        for path in changed
        if len(parts := path.split("/")) >= 2 and parts[0] == "packages"
    }
    return sorted(pkgs)


def _is_exempt(path: str, pkg: str) -> bool:
    """True if ``path`` is a stub/test file that does not count as code.

    The CHANGELOG/MIGRATIONS stubs at the package root are pointers into the
    fragment folders, not code; colocated ``*.test.*`` / ``*.spec.*`` sources
    and anything under a test directory don't change the public API.
    """
    p = re.escape(pkg)
    return bool(
        re.fullmatch(rf"packages/{p}/(CHANGELOG|MIGRATIONS)\.md", path)
        or re.fullmatch(rf"packages/{p}/.*\.(test|spec)\.(ts|tsx|js|py|rs)", path)
        or re.match(rf"packages/{p}/(tests?|__tests__)/", path)
    )


def code_touched(changed: list[str], pkg: str) -> bool:
    """True if the package has non-stub, non-test source changes."""
    prefix = f"packages/{pkg}/"
    return any(
        path.startswith(prefix) and not _is_exempt(path, pkg) for path in changed
    )


def _fragment_name(path: str) -> str | None:
    """The filename if ``path`` sits directly inside a fragment folder."""
    head, _, name = path.rpartition("/")
    return name if head in _FRAGMENT_DIRS else None


def malformed_fragments(changed: list[str]) -> list[str]:
    """Touched fragment files whose names break the naming convention."""
    return [
        path
        for path in changed
        if (name := _fragment_name(path)) is not None
        and name != "README.md"
        and not _FRAGMENT_NAME.fullmatch(name)
    ]


def added_fragments(added: list[str], pkg: str) -> list[str]:
    """Fragments added by the PR that name ``pkg`` after the date prefix."""
    pattern = re.compile(rf"\d{{4}}-\d{{2}}-\d{{2}}-{re.escape(pkg)}-[a-z0-9-]+\.md")
    return [
        path
        for path in added
        if (name := _fragment_name(path)) is not None and pattern.fullmatch(name)
    ]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout


def main() -> int:
    base, head = os.environ["BASE_SHA"], os.environ["HEAD_SHA"]

    if has_skip_trailer(_git("log", "--format=%B", f"{base}..{head}")):
        print("skip-changelog trailer present; bypassing enforcement.")
        return 0

    changed = [p for p in _git("diff", "--name-only", base, head).splitlines() if p]
    added = [
        p
        for p in _git("diff", "--name-only", "--diff-filter=A", base, head).splitlines()
        if p
    ]

    fail = 0
    for path in malformed_fragments(changed):
        print(
            f"::error file={path}::fragment filenames must match "
            f"YYYY-MM-DD-<pkg>-<slug>.md (UTC merge date; lowercase letters, "
            f"digits, hyphens)."
        )
        fail = 1

    packages = changed_packages(changed)
    if not packages and not fail:
        print("No package files touched; nothing to enforce.")
        return 0

    for pkg in packages:
        if not code_touched(changed, pkg):
            continue
        if added_fragments(added, pkg):
            continue
        print(
            f"::error::packages/{pkg} has code changes but no changelog fragment "
            f"was added. Add docs/changelog.d/YYYY-MM-DD-{pkg}-<slug>.md (plus a "
            f"docs/migrations.d/ fragment if the change is breaking), or include "
            f"a 'skip-changelog:' trailer for genuinely internal refactors."
        )
        fail = 1
    return fail


def run(_args: argparse.Namespace) -> int:
    """Entry point for ``ci check-changelog``; same exit codes as ``main()``."""
    return main()


if __name__ == "__main__":
    raise SystemExit(main())
