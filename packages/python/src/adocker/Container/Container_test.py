import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, patch

import pytest

from adocker.Container.Container import Container


@pytest.fixture
def run_docker() -> Iterator[AsyncMock]:
    with patch("adocker.Container.Container.run_docker", autospec=True) as m:
        yield m


def describe_Container() -> None:
    def it_wraps_a_name_with_no_client_stdin_or_command() -> None:
        container = Container("box")
        assert container.name == "box"
        assert container.client is None
        assert container.stdin is None
        assert container.docker_command == []

    def it_keeps_what_it_was_started_with() -> None:
        client, stdin = Mock(), Mock()
        container = Container("box", client=client, stdin=stdin, docker_command=("docker", "run"))
        assert container.client is client
        assert container.stdin is stdin
        assert container.docker_command == ["docker", "run"]

    def it_takes_its_options_by_keyword_only() -> None:
        with pytest.raises(TypeError):
            Container("box", Mock())  # type: ignore[call-arg]

    async def it_stops_with_a_grace_period(run_docker: AsyncMock) -> None:
        await Container("box").stop(5)
        run_docker.assert_awaited_once_with("stop", "--time", "5", "box")

    async def it_force_removes(run_docker: AsyncMock) -> None:
        await Container("box").remove()
        run_docker.assert_awaited_once_with("rm", "--force", "box")

    async def it_inspects(run_docker: AsyncMock) -> None:
        run_docker.return_value = '[{"State": {"Status": "exited"}}]'
        assert await Container("box").inspect() == {"State": {"Status": "exited"}}
        run_docker.assert_awaited_once_with("container", "inspect", "--format", "json", "box")

    def describe_wait() -> None:
        async def it_reads_the_exit_code_docker_wait_prints(run_docker: AsyncMock) -> None:
            run_docker.return_value = "3\n"
            assert await Container("box").wait() == 3
            run_docker.assert_awaited_once_with("wait", "box")

        async def it_returns_the_attached_clients_code(run_docker: AsyncMock) -> None:
            async def client() -> int:
                return 7

            assert await Container("box", client=asyncio.ensure_future(client())).wait() == 7
            run_docker.assert_not_awaited()

        async def it_cancels_the_client_when_cancelled() -> None:
            client = asyncio.ensure_future(asyncio.sleep(3600, 0))
            waiting = asyncio.ensure_future(Container("box", client=client).wait())
            await asyncio.sleep(0)
            waiting.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiting
            assert client.cancelled()

    def describe_exec() -> None:
        async def it_runs_the_command_with_no_stdin_by_default(run_docker: AsyncMock) -> None:
            run_docker.return_value = "out"
            assert await Container("box").exec("sh", "-c", "x") == "out"
            run_docker.assert_awaited_once_with(
                "exec", "box", "sh", "-c", "x", stdin=asyncio.subprocess.DEVNULL
            )

        async def it_runs_interactively_on_a_given_stdin(run_docker: AsyncMock) -> None:
            await Container("box").exec("cat", stdin=9)
            run_docker.assert_awaited_once_with("exec", "--interactive", "box", "cat", stdin=9)

        async def it_runs_without_interactive_on_no_stdin(run_docker: AsyncMock) -> None:
            await Container("box").exec("cat", stdin=None)
            run_docker.assert_awaited_once_with("exec", "box", "cat", stdin=None)

        async def it_raises_what_docker_raised(run_docker: AsyncMock) -> None:
            run_docker.side_effect = RuntimeError("exited 1")
            with pytest.raises(RuntimeError, match="exited 1"):
                await Container("box").exec("false")
