import os
import stat
from contextlib import ExitStack, suppress
from pathlib import Path

_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


def read_transcript(home: Path, pattern: str) -> dict[str, str]:
    """Each regular file under `home` matching `pattern`, by its path relative to `home`.

    The agent writes `home` and may still be running, so each match is opened one component at
    a time from `home` without following links: any link, even one that stays in `home`, is
    skipped, as is anything that isn't a regular file. Bytes that aren't UTF-8 are replaced and
    a file that won't open is skipped, so the agent can't break the run's result.
    """
    transcript = {}
    with ExitStack() as stack:
        home_fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY)
        stack.callback(os.close, home_fd)
        for path in sorted(home.glob(pattern)):
            relative = path.relative_to(home)
            with suppress(OSError):
                text = _read(home_fd, relative.parts)
                if text is not None:
                    transcript[relative.as_posix()] = text
    return transcript


def _read(home_fd: int, parts: tuple[str, ...]) -> str | None:
    if ".." in parts:
        return None
    with ExitStack() as stack:
        dir_fd = home_fd
        for part in parts[:-1]:
            dir_fd = os.open(part, _DIR, dir_fd=dir_fd)
            stack.callback(os.close, dir_fd)
        fd = os.open(parts[-1], _FILE, dir_fd=dir_fd)
    with os.fdopen(fd, encoding="utf-8", errors="replace") as file:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        return file.read()
