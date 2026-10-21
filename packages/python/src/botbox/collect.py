import subprocess
import threading
from collections.abc import Sequence

from python_on_whales import docker
from python_on_whales.exceptions import DockerException

# What the Docker client exits with when it, not the container, failed.
CLIENT_FAILED = 125


def collect(command: Sequence[str]) -> tuple[str, str, int]:
    """Run an attached `docker run` to its exit: the container's stdout, stderr, exit code.

    The client attaches before the container starts, so no output is missed, and it waits out
    a `--rm` container's removal itself, so the exit code survives it. If the daemon goes away
    first, what already arrived is kept, the client's error ends stderr, and the exit code is -1.
    """
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    stderr: list[bytes] = []
    # Drained alongside, so a chatty stderr can't fill its pipe and stall the container.
    reader = threading.Thread(target=stderr.extend, args=(process.stderr,), daemon=True)
    reader.start()
    try:
        stdout = process.stdout.read()
        exit_code = process.wait()
        reader.join()
    except BaseException:
        process.kill()
        process.wait()
        raise
    if exit_code == CLIENT_FAILED:
        try:
            docker.version()
        except DockerException:
            exit_code = -1
    return stdout.decode(errors="replace"), b"".join(stderr).decode(errors="replace"), exit_code
