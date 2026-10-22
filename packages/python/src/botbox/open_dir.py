import os
from pathlib import Path

DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def open_dir(root: Path, parts: tuple[str, ...]) -> int:
    """Open `root`, then each of `parts` below it in turn, failing on any link."""
    fd = os.open(root, DIRECTORY)
    try:
        for part in parts:
            child = os.open(part, DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
    except BaseException:
        os.close(fd)
        raise
    return fd
