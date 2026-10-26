import warnings
from collections.abc import Sequence

from adocker.DockerException import DockerException
from adocker.inspect_container import inspect_container
from adocker.version import version


async def agent_exit(container: str, command: Sequence[str], client: int, stderr: str) -> int:
    """The exit code of `container`, once `command`, its attached client, exited with `client`.

    The container's own record decides, so a command that exits 125 is told apart from a client
    that failed. -1 if the daemon went away. Raises DockerException, with the client's code and
    stderr, if the container never ran to its exit, or the client was killed, while the daemon
    was up: output read through a killed client may be cut short. Warns if the kernel killed it
    for going over its memory cap.
    """
    try:
        state = (await inspect_container(container))["State"]
    except DockerException:
        try:
            await version()
        except DockerException:
            return -1
        state = {}
    if client < 0 or state.get("Status") != "exited":
        raise DockerException(command, client, stderr)
    code: int = state["ExitCode"]
    if state.get("OOMKilled"):
        warnings.warn(
            f"botbox's container {container} ran out of memory and was killed (exit {code}): "
            "raise Botbox(limits=Limits(memory=...))",
            RuntimeWarning,
            stacklevel=2,
        )
    return code
