import asyncio
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from adocker.Image.Image import Image, attach

DEVNULL = asyncio.subprocess.DEVNULL
PIPE = asyncio.subprocess.PIPE


@pytest.fixture(autouse=True)
def run_docker() -> Iterator[AsyncMock]:
    with patch("adocker.Image.Image.run_docker", autospec=True, return_value="id\n") as m:
        yield m


@pytest.fixture(autouse=True)
def inspect() -> Iterator[AsyncMock]:
    with patch(
        "adocker.Image.Image.Container.inspect", autospec=True, return_value={"Created": "T"}
    ) as m:
        yield m


@pytest.fixture
def up() -> asyncio.Event:
    """Set when the daemon reports the container started."""
    event = asyncio.Event()
    event.set()
    return event


@pytest.fixture(autouse=True)
def started(up: asyncio.Event) -> Iterator[AsyncMock]:
    async def reported(_container: object, _since: str) -> None:
        await up.wait()

    with patch("adocker.Image.Image.started", autospec=True, side_effect=reported) as m:
        yield m


@pytest.fixture
def calls() -> list[dict[str, Any]]:
    return []


@pytest.fixture
def release() -> asyncio.Event:
    """Set to let the fake client exit, with code 3."""
    return asyncio.Event()


@pytest.fixture(autouse=True)
def execute(calls: list[dict[str, Any]], release: asyncio.Event) -> Iterator[AsyncMock]:
    async def client(args: list[str], **options: Any) -> int:
        calls.append({"args": args, **options})
        options["started"].set_result(None)
        await release.wait()
        return 3

    with patch("adocker.Image.Image.execute", autospec=True, side_effect=client) as m:
        yield m


class StdinPipe:
    """Stands in for adocker's StdinPipe, so `attach` can tell it from a plain stdin."""

    def __init__(self) -> None:
        self.read = 11
        self.writer = Mock()
        self.release = Mock()


@pytest.fixture(autouse=True)
def stdin_pipe() -> Iterator[type[StdinPipe]]:
    with patch("adocker.Image.Image.StdinPipe", StdinPipe):
        yield StdinPipe


@pytest.fixture
def pipe() -> Iterator[Any]:
    made = StdinPipe()
    with patch.object(StdinPipe, "open", AsyncMock(return_value=made), create=True):
        yield made


def describe_Image() -> None:
    async def it_inspects(run_docker: AsyncMock) -> None:
        run_docker.return_value = '[{"Id": "sha256:abc"}]'
        assert await Image("x:latest").inspect() == {"Id": "sha256:abc"}
        run_docker.assert_awaited_once_with("image", "inspect", "--format", "json", "x:latest")

    def describe_run() -> None:
        async def it_creates_the_container_then_starts_it_attached(
            run_docker: AsyncMock,
            inspect: AsyncMock,
            started: AsyncMock,
            calls: list[dict[str, Any]],
            release: asyncio.Event,
        ) -> None:
            container = await Image("img").run("sh", "-c", "x", name="box")
            run_docker.assert_awaited_once_with("create", "--name", "box", "img", "sh", "-c", "x")
            [(inspected,)] = [c.args for c in inspect.await_args_list]
            assert inspected.name == "box"
            [(watched, since)] = [c.args for c in started.await_args_list]
            assert (watched.name, since) == ("box", "T")
            assert container.name == "box"
            assert container.stdin is None
            assert container.docker_command == ["docker", "start", "--attach", "box"]
            [call] = calls
            assert call["args"] == ["start", "--attach", "box"]
            assert call["stdin"] == DEVNULL
            assert call["stdout"] == DEVNULL
            assert call["stderr"] == DEVNULL
            assert container.client is not None
            assert not container.client.done()
            release.set()
            assert await container.wait() == 3

        async def it_returns_only_once_the_container_is_running(up: asyncio.Event) -> None:
            up.clear()
            task = asyncio.create_task(Image("img").run(name="box"))
            await asyncio.sleep(0.01)
            assert not task.done()
            up.set()
            assert (await task).name == "box"

        async def it_returns_a_client_that_exits_before_the_start_is_reported(
            up: asyncio.Event, release: asyncio.Event, started: AsyncMock
        ) -> None:
            up.clear()
            release.set()
            container = await Image("img").run(name="box")
            assert await container.wait() == 3
            started.assert_awaited_once()

        async def it_raises_when_the_container_cant_be_created(
            run_docker: AsyncMock, execute: AsyncMock, pipe: Mock
        ) -> None:
            run_docker.side_effect = OSError("no such image")
            with pytest.raises(OSError, match="no such image"):
                await Image("img").run(name="box", stdin=PIPE)
            execute.assert_not_called()
            pipe.writer.close.assert_not_called()

        async def it_kills_the_client_when_the_start_cant_be_watched(
            started: AsyncMock, pipe: Mock, calls: list[dict[str, Any]]
        ) -> None:
            started.side_effect = OSError("events failed")
            with pytest.raises(OSError, match="events failed"):
                await Image("img").run(name="box", stdin=PIPE)
            assert len(calls) == 1
            pipe.release.assert_called_once_with()
            pipe.writer.close.assert_called_once_with()

        async def it_hands_its_sinks_to_the_client(calls: list[dict[str, Any]]) -> None:
            out, err = Mock(), Mock()
            await Image("img").run(name="box", stdout=out, stderr=err)
            assert calls[0]["stdout"] is out
            assert calls[0]["stderr"] is err

        async def it_passes_every_option_as_a_flag(
            run_docker: AsyncMock, calls: list[dict[str, Any]]
        ) -> None:
            await Image("img").run(
                "cmd",
                name="box",
                stdin=9,
                init=True,
                rm=True,
                labels={"a": "1"},
                user="1:2",
                env={"K": "v"},
                mounts=[Mock(volume_flag="vol:/run:ro")],
                tmpfs=["/t"],
                workdir="/w",
                network="none",
                pid="container:p",
                pids_limit=64,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                log_driver="none",
                entrypoint="sh",
            )
            assert calls[0]["stdin"] == 9
            assert calls[0]["args"] == ["start", "--attach", "--interactive", "box"]
            run_docker.assert_awaited_once_with(
                "create",
                "--interactive",
                "--init",
                "--rm",
                "--name",
                "box",
                "--label",
                "a=1",
                "--user",
                "1:2",
                "--env",
                "K=v",
                "--volume",
                "vol:/run:ro",
                "--tmpfs",
                "/t",
                "--workdir",
                "/w",
                "--network",
                "none",
                "--pid",
                "container:p",
                "--pids-limit",
                "64",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--log-driver",
                "none",
                "--entrypoint",
                "sh",
                "img",
                "cmd",
            )

        async def it_is_not_interactive_on_an_inherited_stdin(
            run_docker: AsyncMock, calls: list[dict[str, Any]]
        ) -> None:
            await Image("img").run(name="box", stdin=None)
            assert "--interactive" not in run_docker.await_args_list[0].args
            assert "--interactive" not in calls[0]["args"]
            assert calls[0]["stdin"] is None

        async def it_gives_a_pipe_its_read_end_and_the_container_its_writer(
            calls: list[dict[str, Any]], pipe: Mock, release: asyncio.Event
        ) -> None:
            writer: Mock = pipe.writer
            container = await Image("img").run(name="box", stdin=PIPE)
            assert container.stdin is writer
            assert "--interactive" in calls[0]["args"]
            assert calls[0]["stdin"] == 11
            pipe.release.assert_not_called()
            release.set()
            await container.wait()
            pipe.release.assert_called_once_with()
            writer.close.assert_not_called()

        async def it_raises_a_client_that_fails_to_start_and_closes_the_pipe(
            execute: AsyncMock, pipe: Mock, up: asyncio.Event
        ) -> None:
            up.clear()
            execute.side_effect = FileNotFoundError("docker")
            with pytest.raises(FileNotFoundError):
                await Image("img").run(name="box", stdin=PIPE)
            pipe.release.assert_called_once_with()
            pipe.writer.close.assert_called_once_with()

        async def it_raises_a_client_that_fails_to_start_without_a_pipe(
            execute: AsyncMock, up: asyncio.Event
        ) -> None:
            up.clear()
            execute.side_effect = FileNotFoundError("docker")
            with pytest.raises(FileNotFoundError):
                await Image("img").run(name="box")

        async def it_returns_a_client_that_started_and_then_failed(
            execute: AsyncMock, up: asyncio.Event
        ) -> None:
            up.clear()

            async def client(_args: list[str], **options: Any) -> int:
                options["started"].set_result(None)
                raise OSError("disk full")

            execute.side_effect = client
            container = await Image("img").run(name="box")
            with pytest.raises(OSError, match="disk full"):
                await container.wait()

        async def it_cancels_and_settles_the_client_when_cancelled_before_it_starts(
            execute: AsyncMock, pipe: Mock, up: asyncio.Event
        ) -> None:
            up.clear()
            starting, release, finished = asyncio.Event(), asyncio.Event(), Mock()

            async def client(_args: list[str], **_options: Any) -> int:
                starting.set()
                try:
                    await asyncio.sleep(3600)
                finally:
                    await release.wait()
                    finished()
                return 0

            execute.side_effect = client
            task = asyncio.create_task(Image("img").run(name="box", stdin=PIPE))
            await starting.wait()
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            finished.assert_called_once_with()
            pipe.release.assert_called_once_with()
            pipe.writer.close.assert_called_once_with()

        async def it_takes_its_options_by_keyword_only() -> None:
            with pytest.raises(TypeError):
                await Image("img").run(name="box", stdin=DEVNULL, bogus=1)  # type: ignore[call-arg]


def describe_attach() -> None:
    async def it_lets_go_of_the_pipe_when_the_client_fails() -> None:
        pipe = StdinPipe()
        started: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        with (
            patch("adocker.Image.Image.execute", AsyncMock(side_effect=OSError("boom"))),
            pytest.raises(OSError, match="boom"),
        ):
            await attach(["start"], pipe, None, None, started)  # type: ignore[arg-type]
        pipe.release.assert_called_once_with()

    async def it_passes_a_plain_stdin_through() -> None:
        started: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        with patch("adocker.Image.Image.execute", AsyncMock(return_value=0)) as execute:
            assert await attach(["start"], 9, None, None, started) == 0
        execute.assert_awaited_once_with(
            ["start"], stdin=9, stdout=DEVNULL, stderr=DEVNULL, started=started
        )
