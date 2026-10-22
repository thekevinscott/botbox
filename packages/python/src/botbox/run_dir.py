import os
import stat
from contextlib import suppress
from pathlib import Path
from tempfile import gettempdir


def run_dir() -> Path:
    """This user's dir for runs' locks and temp homes, in the system temp dir, made owner-only.

    One that isn't a real dir this user owns and alone can open is refused: in a shared temp
    dir, another user could have made it first.
    """
    path = Path(gettempdir()) / f"botbox-{os.getuid()}"
    with suppress(FileExistsError):
        path.mkdir(mode=0o700)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError(
            f"botbox won't keep runs in {path}: it must be a dir only you can open"
        )
    return path
