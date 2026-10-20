import signal
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from types import FrameType

_held = 0


def _unwind(signum: int, _frame: FrameType | None) -> None:
    raise SystemExit(128 + signum)


@contextmanager
def sigterm_unwinds() -> Iterator[None]:
    """While held, SIGTERM raises `SystemExit` so `finally` blocks and `__exit__` run.

    Python's default SIGTERM exits without unwinding, which strands containers. Only the
    default handler is replaced; a handler the program installed is left alone. Handlers can
    only be set from the main thread, so elsewhere this does nothing.
    """
    global _held
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    if _held == 0 and signal.getsignal(signal.SIGTERM) is signal.SIG_DFL:
        signal.signal(signal.SIGTERM, _unwind)
    _held += 1
    try:
        yield
    finally:
        _held -= 1
        if _held == 0 and signal.getsignal(signal.SIGTERM) is _unwind:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
