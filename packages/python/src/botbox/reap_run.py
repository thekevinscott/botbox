import asyncio
import fcntl
import os
import warnings
from pathlib import Path

from botbox.docker.run_docker import run_docker
from botbox.remove_tree import remove_tree


async def reap_run(lock: Path) -> bool:
    """Remove the run `lock` names, if its owner is dead, and say whether it did.

    Dead means the lock is free. Its containers go first, in any state, including one created
    and never started; then its temp home; then the lock file. A step that fails is a warning,
    and the lock file stays for the next sweep.
    """
    token = lock.stem
    try:
        fd = os.open(lock, os.O_RDONLY)
    except FileNotFoundError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        if not os.fstat(fd).st_nlink:
            return False
        try:
            found = await run_docker(
                "ps", "--all", "--quiet", "--filter", f"label=botbox.run={token}"
            )
            if containers := found.split():
                await run_docker("rm", "--force", *containers)
            await asyncio.to_thread(remove_tree, lock.with_suffix(""))
            lock.unlink()
        except Exception as error:
            warnings.warn(
                f"botbox could not reap run {token}: {error}", RuntimeWarning, stacklevel=2
            )
            return False
        return True
    finally:
        os.close(fd)
