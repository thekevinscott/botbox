import re
from pathlib import Path

NUMBERED = re.compile(r"^(?:(?:stdout|stderr)\.(\d+)\.txt|(?:proxy|credentials)\.(\d+)\.log)$")


def numbered(folder: Path) -> dict[Path, int]:
    """The restart log files in `folder`, each with its attempt number."""
    found = {}
    for path in folder.iterdir():
        match = NUMBERED.match(path.name)
        if match:
            found[path] = int(match.group(1) or match.group(2))
    return found


def next_attempt(folder: Path) -> int:
    """The number for a restart's log files: one past the highest in `folder`, from 1."""
    return max(numbered(folder).values(), default=0) + 1


def clear_attempts(folder: Path) -> None:
    """Remove a previous run's restart log files, so a new run's restarts number from 1."""
    for path in numbered(folder):
        path.unlink()
