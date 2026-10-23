import os
import stat
from contextlib import suppress
from pathlib import Path

from botbox.open_dir import DIRECTORY, open_dir


def move_transcript(home: Path, pattern: str, staging: Path, dest: Path) -> None:
    """Move each regular file under `home` matching `pattern` to its path relative to `home` in
    `dest`, without reading it.

    The agent writes `home` and may still be running, so no link is followed: each match is
    reached one dir at a time, renamed into `staging`, which the agent can't reach, and kept
    only if it is a regular file there, made readable to its owner. What isn't kept stays in
    `staging`. `staging` and `dest` must be on `home`'s filesystem; a file that won't move is
    skipped.
    """
    dest.mkdir(mode=0o700)
    staging.mkdir(mode=0o700)
    staged = os.open(staging, DIRECTORY)
    try:
        for index, path in enumerate(sorted(home.glob(pattern))):
            relative = path.relative_to(home)
            with suppress(OSError):
                parent = open_dir(home, relative.parts[:-1])
                try:
                    os.rename(relative.name, str(index), src_dir_fd=parent, dst_dir_fd=staged)
                finally:
                    os.close(parent)
                if stat.S_ISREG(os.stat(str(index), dir_fd=staged, follow_symlinks=False).st_mode):
                    target = dest / relative
                    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    os.rename(str(index), target, src_dir_fd=staged)
                    target.chmod(0o600)
    finally:
        os.close(staged)
