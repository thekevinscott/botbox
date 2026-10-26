from adocker import Container, Daemon, DockerException


async def agent_exit(container: Container, client: int, stderr: str) -> int:
    """The exit code of `container`, once its attached client exited with `client`.

    The container's own record decides, so a command that exits 125 is told apart from a client
    that failed. -1 if the daemon went away. Raises DockerException, with the client's code and
    stderr, if the container never ran to its exit, or the client was killed, while the daemon
    was up: output read through a killed client may be cut short.
    """
    try:
        state = (await container.inspect())["State"]
    except DockerException:
        try:
            await Daemon().version()
        except DockerException:
            return -1
        state = {}
    if client < 0 or state.get("Status") != "exited":
        raise DockerException(container.docker_command, client, stderr)
    code: int = state["ExitCode"]
    return code
