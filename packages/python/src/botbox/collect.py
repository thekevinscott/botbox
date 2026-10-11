from collections.abc import Iterable
from typing import cast

from python_on_whales import docker
from python_on_whales.components.container.cli_wrapper import Container
from python_on_whales.exceptions import DockerException


def collect(container: Container | str) -> tuple[str, str, int]:
    """Follow a container to its exit: its stdout, its stderr, and its exit code.

    Output streams to the host as the container writes it. If the daemon goes away first,
    what already arrived is kept and the exit code is -1.
    """
    output: dict[str, list[bytes]] = {"stdout": [], "stderr": []}
    exit_code = -1
    try:
        # stream=True makes logs() yield (source, chunk) pairs instead of returning a str.
        stream = cast(Iterable[tuple[str, bytes]], docker.logs(container, follow=True, stream=True))
        for source, chunk in stream:
            output[source].append(chunk)
        exit_code = docker.wait(container)
    except DockerException:
        pass  # The daemon died mid-run: return what arrived rather than raise.
    stdout, stderr = (b"".join(output[s]).decode(errors="replace") for s in ("stdout", "stderr"))
    return stdout, stderr, exit_code
