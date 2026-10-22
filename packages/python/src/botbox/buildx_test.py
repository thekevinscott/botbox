import asyncio
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from botbox.buildx import buildx

STDERR_LIMIT = 64 * 1024

ARGV = [
    "docker",
    "buildx",
    "build",
    "--load",
    "--progress=quiet",
    "--tag",
    "an-agent:latest",
    "--file",
    "/agents/Dockerfile",
    "--build-context",
    "botbox=/relay",
    "/agents",
]


class DockerException(Exception):
    """Stands in for python_on_whales' DockerException."""

    def __init__(self, command: list[str], return_code: int, *, stderr: bytes) -> None:
        self.docker_command = command
        self.return_code = return_code
        self.stderr = stderr.decode()


@pytest.fixture(autouse=True)
def docker_exception() -> Iterator[None]:
    with patch("botbox.buildx.DockerException", DockerException):
        yield


class Process:
    """The buildx client: writes `stderr`, then exits with `code`, unless it hangs mid-build."""

    def __init__(self, stderr: bytes = b"", code: int = 0, *, hangs: bool = False) -> None:
        self.stderr = asyncio.StreamReader()
        self.stderr.feed_data(stderr)
        self.returncode: int | None = None
        self.code = code
        self.terminate = Mock(side_effect=self.exit)
        if not hangs:
            self.exit()

    def exit(self) -> None:
        self.stderr.feed_eof()
        self.returncode = self.code if self.returncode is None else self.returncode

    async def wait(self) -> int:
        while self.returncode is None:
            await asyncio.sleep(0)
        return self.returncode


@pytest.fixture
async def process() -> Process:
    return Process()


@pytest.fixture(autouse=True)
def spawn(process: Process) -> Iterator[AsyncMock]:
    with patch("botbox.buildx.asyncio.create_subprocess_exec", autospec=True) as m:
        m.return_value = process
        yield m


async def build() -> None:
    await buildx(
        Path("/agents"),
        tag="an-agent:latest",
        file=Path("/agents/Dockerfile"),
        contexts={"botbox": Path("/relay")},
    )


def describe_buildx() -> None:
    async def it_runs_a_quiet_buildx_build_that_loads_the_image(spawn: AsyncMock) -> None:
        await build()
        spawn.assert_awaited_once_with(
            *ARGV,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

    async def it_passes_no_build_context_flag_without_contexts(spawn: AsyncMock) -> None:
        await buildx(
            Path("/layer"), tag="a-layer:latest", file=Path("/layer/Dockerfile"), contexts={}
        )
        assert "--build-context" not in spawn.call_args.args

    async def it_takes_its_options_by_keyword_only() -> None:
        with pytest.raises(TypeError):
            await buildx(Path("/layer"), "a-layer:latest", Path("/layer/Dockerfile"), {})  # type: ignore[call-arg]

    def describe_when_the_client_is_killed() -> None:
        @pytest.fixture
        async def process() -> Process:
            return Process(code=-9)

        async def it_raises() -> None:
            with pytest.raises(DockerException) as error:
                await build()
            assert error.value.return_code == -9

    def describe_when_the_build_fails() -> None:
        @pytest.fixture
        async def process() -> Process:
            return Process(b"ERROR: failed to build: failed to solve\n", 1)

        async def it_raises_with_the_command_exit_code_and_stderr() -> None:
            with pytest.raises(DockerException) as error:
                await build()
            assert error.value.docker_command == ARGV
            assert error.value.return_code == 1
            assert error.value.stderr == "ERROR: failed to build: failed to solve\n"

    def describe_when_stderr_runs_long() -> None:
        @pytest.fixture
        async def process() -> Process:
            return Process(b"a" * STDERR_LIMIT + "é".encode() + b"b" * (STDERR_LIMIT - 1), 1)

        async def it_keeps_only_the_tail() -> None:
            with pytest.raises(DockerException) as error:
                await build()
            assert error.value.stderr == "�" + "b" * (STDERR_LIMIT - 1)

    def describe_when_cancelled_mid_build() -> None:
        @pytest.fixture
        async def process() -> Process:
            return Process(hangs=True)

        async def it_terminates_the_client_and_waits_for_it(process: Process) -> None:
            task = asyncio.create_task(build())
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            process.terminate.assert_called_once_with()
            assert process.returncode is not None
