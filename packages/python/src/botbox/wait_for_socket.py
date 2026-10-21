import subprocess
import time
from pathlib import Path


def wait_for_socket(
    socket: Path, process: subprocess.Popen[bytes], output: Path, timeout: float
) -> None:
    """Return once `socket` exists. Raise with `output` if `process` exits or `timeout` passes."""
    deadline = time.monotonic() + timeout
    while not socket.exists():
        if process.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError(f"botbox proxy did not start:\n{output.read_text()}")
        time.sleep(0.05)
