from adocker.DockerException import DockerException


def describe_docker_exception() -> None:
    def it_keeps_the_command_exit_code_and_stderr() -> None:
        error = DockerException(["docker", "version"], 1, "Cannot connect")
        assert error.docker_command == ["docker", "version"]
        assert error.return_code == 1
        assert error.stderr == "Cannot connect"

    def it_says_what_ran_and_what_it_said() -> None:
        assert str(DockerException(["docker", "version"], 1, "Cannot connect")) == (
            "`docker version` exited 1:\nCannot connect"
        )
