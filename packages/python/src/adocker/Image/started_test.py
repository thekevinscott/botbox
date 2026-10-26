import asyncio
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from adocker.Image.started import started

BOX: Any = SimpleNamespace(name="box")


class DockerException(Exception):
    def __init__(self, docker_command: list[str], return_code: int, stderr: str) -> None:
        self.docker_command = docker_command
        self.return_code = return_code
        self.stderr = stderr


@pytest.fixture(autouse=True)
def docker_exception() -> Iterator[None]:
    with patch("adocker.Image.started.DockerException", DockerException):
        yield


@pytest.fixture
def printed() -> list[bytes]:
    """What the event stream prints before it blocks, or ends if `ends` is set."""
    return [b"start\n"]


@pytest.fixture
def ends() -> list[bool]:
    return [False]


@pytest.fixture
def cancelled() -> Mock:
    return Mock()


@pytest.fixture(autouse=True)
def run_docker(printed: list[bytes], ends: list[bool], cancelled: Mock) -> Iterator[AsyncMock]:
    async def stream(*_args: str, stdout: Any) -> str:
        for chunk in printed:
            stdout(chunk)
        if ends[0]:
            return ""
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled()
            raise
        return ""

    with patch("adocker.Image.started.run_docker", autospec=True, side_effect=stream) as m:
        yield m


def describe_started() -> None:
    async def it_watches_for_the_containers_start_since_it_was_created(
        run_docker: AsyncMock,
    ) -> None:
        await started(BOX, "2026-01-01T00:00:00Z")
        assert run_docker.await_args is not None
        assert run_docker.await_args.args == (
            "events",
            "--since",
            "2026-01-01T00:00:00Z",
            "--filter",
            "container=box",
            "--filter",
            "event=start",
            "--format",
            "{{.Action}}",
        )

    async def it_stops_the_stream_once_it_has_seen_the_start(cancelled: Mock) -> None:
        await started(BOX, "T")
        cancelled.assert_called_once_with()

    async def it_raises_when_the_stream_ends_without_a_start(
        printed: list[bytes], ends: list[bool]
    ) -> None:
        printed.clear()
        ends[0] = True
        with pytest.raises(DockerException) as raised:
            await started(BOX, "T")
        assert raised.value.docker_command[:2] == ["docker", "events"]
        assert raised.value.return_code == 0

    async def it_raises_what_the_stream_raised(run_docker: AsyncMock) -> None:
        run_docker.side_effect = OSError("daemon gone")
        with pytest.raises(OSError, match="daemon gone"):
            await started(BOX, "T")

    async def it_stops_the_stream_when_cancelled(printed: list[bytes], cancelled: Mock) -> None:
        printed.clear()
        task = asyncio.create_task(started(BOX, "T"))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        cancelled.assert_called_once_with()
