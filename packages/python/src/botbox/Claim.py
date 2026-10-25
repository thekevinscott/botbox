import fcntl

from botbox.linux_tools.process.close_held import HELD
from botbox.remove_tree import remove_tree
from botbox.run_dir import run_dir


class Claim:
    """A run's temp dir, `<run dir>/<token>`, and the lock beside it that says its owner lives.

    The lock is an exclusive `flock` on `<token>.lock`, outside every mount, so the kernel
    drops it however the owner dies and `reap()` can tell. It is taken on a hidden name first,
    so a sweep never sees the lock file's name unlocked while its owner lives. Forked children
    close it, so one that outlives the owner can't keep a dead run looking alive.
    """

    def __init__(self, token: str) -> None:
        root = run_dir()
        self.path = root / token
        self.lock = root / f"{token}.lock"
        pending = root / f".{token}.pending"
        self._held = pending.open("xb")
        try:
            fcntl.flock(self._held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                self.lock.hardlink_to(pending)
            finally:
                pending.unlink()
            self.path.mkdir(mode=0o700)
        except BaseException:
            self._held.close()
            raise
        HELD.add(self._held)

    def cleanup(self) -> None:
        """Remove the dir, then the lock file, and let go.

        A dir that won't go keeps its lock file, so a later `reap()` tries again.
        """
        try:
            remove_tree(self.path)
            self.lock.unlink()
        finally:
            HELD.discard(self._held)
            self._held.close()
