from contextlib import suppress
from pathlib import Path


def read_transcript(home: Path, pattern: str) -> dict[str, str]:
    """Each file under `home` matching `pattern`, by its path relative to `home`.

    The agent writes `home`, so a match that resolves outside it is a link to a host file and
    is skipped. The container has exited by the time this runs, so no link can change after
    the check. Bytes that aren't UTF-8 are replaced and a file that won't open is skipped, so
    the agent can't break the run's result.
    """
    root = home.resolve()
    transcript = {}
    for path in sorted(home.glob(pattern)):
        if path.is_file() and path.resolve().is_relative_to(root):
            with suppress(OSError):
                transcript[path.relative_to(home).as_posix()] = path.read_text(
                    encoding="utf-8", errors="replace"
                )
    return transcript
