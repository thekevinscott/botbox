from adocker import Container, DockerException


async def agent_exit(container: Container, client: int, stderr: str) -> int:
    """The exit code of `container`, once its attached client exited with `client`.

    The container's own record decides, so a command that exits 125 is told apart from a client
    that failed. Raises DockerException, with the client's code and stderr, if the container
    can't be inspected, never ran to its exit, or the client was killed: output read through a
    killed client may be cut short.
    """
    try:
        state = (await container.inspect())["State"]
    except DockerException:
        raise DockerException(container.docker_command, client, stderr) from None
    if client < 0 or state.get("Status") != "exited":
        raise DockerException(container.docker_command, client, stderr)
    code: int = state["ExitCode"]
    return code
