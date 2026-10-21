import subprocess
from contextlib import suppress
from typing import IO


def stop_attached(process: subprocess.Popen[bytes], stdin: IO[bytes], timeout: float) -> None:
    """End an attached container by closing `stdin`. Kill the attach if it outlives `timeout`."""
    with suppress(OSError):
        stdin.close()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
