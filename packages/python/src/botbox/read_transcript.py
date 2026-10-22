import os
import stat
from contextlib import ExitStack, suppress
from pathlib import Path

_DIR = os.O_DIRECTORY | os.O_NOFOLLOW
_FILE = os.O_NOFOLLOW | os.O_NONBLOCK


def read_transcript(home: Path, pattern: str) -> dict[str, str]:
    """Each regular file under `home` matching `pattern`, by its path relative to `home`.

    The agent writes `home` and may still be running, so each match is opened one component at
    a time from `home` without following links: any link, even one that stays in `home`, is
    skipped, as is anything that isn't a regular file. Bytes that aren't UTF-8 are replaced and
    a file that won't open is skipped, so the agent can't break the run's result.
    """
    transcript = {}
    home_fd = os.open(home, os.O_DIRECTORY)
    try:
        for path in sorted(home.glob(pattern)):
            relative = path.relative_to(home)
            *dirs, name = relative.parts
            with suppress(OSError), ExitStack() as stack:
                dir_fd = home_fd
                for part in dirs:
                    dir_fd = os.open(part, _DIR, dir_fd=dir_fd)
                    stack.callback(os.close, dir_fd)
                file = stack.enter_context(
                    os.fdopen(
                        os.open(name, _FILE, dir_fd=dir_fd), encoding="utf-8", errors="replace"
                    )
                )
                if stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                    transcript[relative.as_posix()] = file.read()
    finally:
        os.close(home_fd)
    return transcript
