from collections.abc import Sequence

from botbox.docker.DockerException import DockerException
from botbox.docker.inspect_container import inspect_container
from botbox.docker.version import version


async def agent_exit(container: str, command: Sequence[str], client: int, stderr: str) -> int:
    """The exit code of `container`, once `command`, its attached client, exited with `client`.

    The container's own record decides, so a command that exits 125 is told apart from a client
    that failed. -1 if the daemon went away. Raises DockerException, with the client's code and
    stderr, if the container never ran to its exit while the daemon was up.
    """
    try:
        state = (await inspect_container(container))["State"]
    except DockerException:
        try:
            await version()
        except DockerException:
            return -1
        state = {}
    if state.get("Status") != "exited":
        raise DockerException(command, client, stderr)
    code: int = state["ExitCode"]
    return code
