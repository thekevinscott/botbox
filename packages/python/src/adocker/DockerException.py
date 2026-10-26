from collections.abc import Sequence


class DockerException(Exception):
    """A `docker` command that exited non-zero: what ran, its exit code, and what it said."""

    def __init__(self, docker_command: Sequence[str], return_code: int, stderr: str) -> None:
        self.docker_command = list(docker_command)
        self.return_code = return_code
        self.stderr = stderr
        super().__init__(f"`{' '.join(docker_command)}` exited {return_code}:\n{stderr}")
