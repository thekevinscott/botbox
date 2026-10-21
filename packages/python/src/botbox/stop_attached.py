import subprocess
from contextlib import suppress


def stop_attached(process: subprocess.Popen[bytes], timeout: float) -> None:
    """End an attached container by closing its stdin. Kill the attach if it outlives `timeout`."""
    assert process.stdin is not None
    with suppress(OSError):
        process.stdin.close()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
