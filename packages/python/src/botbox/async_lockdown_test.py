import argparse
import asyncio
from collections.abc import AsyncIterator, Awaitable, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import IO, Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from botbox.async_lockdown import OUTPUT_LIMIT, async_lockdown

ALLOW = ("api.anthropic.com",)
REFUSAL = 'NOTICE Proxying refused on filtered url "github.com:443"\n'
TOKEN = "0123456789ab"
PROXY = "botbox-proxy-0123456789ab"


@pytest.fixture
def steps() -> list[str]:
    return []


@pytest.fixture(autouse=True)
def lock(steps: list[str]) -> Iterator[None]:
    @asynccontextmanager
    async def lock(tag: str) -> AsyncIterator[None]:
        steps.append(f"lock {tag}")
        try:
            yield
        finally:
            steps.append(f"unlock {tag}")

    with patch("botbox.async_lockdown.async_build_lock", lock):
        yield


@pytest.fixture(autouse=True)
def build(steps: list[str]) -> Iterator[AsyncMock]:
    async def built(_context: Path, *, tag: str, **_options: Any) -> None:
        steps.append(f"build {tag}")

    with patch("botbox.async_lockdown.build", autospec=True, side_effect=built) as m:
        yield m


@pytest.fixture
def served() -> asyncio.Event:
    """Set to let the proxy's attached client exit."""
    return asyncio.Event()


@pytest.fixture(autouse=True)
def run(served: asyncio.Event, steps: list[str]) -> Iterator[AsyncMock]:
    async def attached(_args: list[str], **_options: Any) -> int:
        steps.append("run proxy")
        await served.wait()
        return 0

    with patch("botbox.async_lockdown.run", autospec=True, side_effect=attached) as m:
        yield m


@pytest.fixture(autouse=True)
def wait(steps: list[str]) -> Iterator[AsyncMock]:
    async def up(*_args: object) -> None:
        await asyncio.sleep(0)
        steps.append("proxy up")

    with patch("botbox.async_lockdown.wait_for_proxy", autospec=True, side_effect=up) as m:
        yield m


@pytest.fixture(autouse=True)
def stop(served: asyncio.Event, steps: list[str]) -> Iterator[AsyncMock]:
    async def stopped(client: asyncio.Future[int], stdin: IO[bytes], *_args: object) -> None:
        stdin.close()
        served.set()
        await client
        steps.append("proxy stopped")

    with patch("botbox.async_lockdown.stop_proxy", autospec=True, side_effect=stopped) as m:
        yield m


@pytest.fixture(autouse=True)
def settle(steps: list[str]) -> Iterator[AsyncMock]:
    async def settled(step: Awaitable[None]) -> None:
        steps.append("settle")
        await step

    with patch("botbox.async_lockdown.settle", autospec=True, side_effect=settled) as m:
        yield m


@pytest.fixture(autouse=True)
def owned() -> Iterator[set[IO[bytes]]]:
    """Stands in for owner_only: the pipes it holds, while it holds them."""
    pipes: set[IO[bytes]] = set()

    @contextmanager
    def owner_only(pipe: IO[bytes]) -> Iterator[None]:
        pipes.add(pipe)
        try:
            yield
        finally:
            pipes.discard(pipe)

    with patch("botbox.async_lockdown.owner_only", owner_only):
        yield pipes


@pytest.fixture(autouse=True)
def os() -> Iterator[MagicMock]:
    with patch("botbox.async_lockdown.os", autospec=True) as m:
        m.pipe.return_value = (3, 4)
        m.fdopen.side_effect = lambda _fd, _mode: Mock()
        yield m


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    return tmp_path


def jail(scratch: Path, allow: tuple[str, ...] = ALLOW) -> Any:
    return async_lockdown(allow, scratch, TOKEN)


RUN = argparse.ArgumentParser()
for flag in ("--interactive", "--init"):
    RUN.add_argument(flag, action="store_true")
for flag in ("--name", "--user", "--pids-limit", "--label"):
    RUN.add_argument(flag)
for flag in ("--network", "--cap-drop", "--security-opt", "--volume"):
    RUN.add_argument(flag, action="append", default=[])
RUN.add_argument("image")


def started(run: AsyncMock) -> dict[str, Any]:
    """The options of the proxy's `docker run`; an unexpected flag fails the parse."""
    [args] = run.call_args.args
    return vars(RUN.parse_args(args))


def volumes(run: AsyncMock) -> dict[str, tuple[Path, str]]:
    mounts = (volume.split(":") for volume in started(run)["volume"])
    return {target: (Path(source), mode) for source, target, mode in mounts}


def describe_async_lockdown() -> None:
    async def it_yields_what_a_locked_down_container_needs(scratch: Path) -> None:
        async with jail(scratch) as net:
            assert net.proxy == PROXY
            assert net.sockets == scratch / "sockets"
            url = "http://127.0.0.1:41893"
            assert net.envs == {
                "HTTP_PROXY": url,
                "HTTPS_PROXY": url,
                "http_proxy": url,
                "https_proxy": url,
                "NO_PROXY": "localhost,127.0.0.1",
            }

    async def it_builds_the_shipped_proxy_under_its_tags_lock_first(
        scratch: Path, build: AsyncMock, steps: list[str]
    ) -> None:
        async with jail(scratch):
            pass
        [context] = build.call_args.args
        assert build.call_args.kwargs == {
            "tag": "botbox-proxy:latest",
            "file": context / "Dockerfile",
        }
        assert (context / "tinyproxy.conf").exists()
        assert steps[:4] == [
            "lock botbox-proxy:latest",
            "build botbox-proxy:latest",
            "unlock botbox-proxy:latest",
            "run proxy",
        ]

    async def it_starts_nothing_when_the_build_fails(
        scratch: Path, build: AsyncMock, run: AsyncMock
    ) -> None:
        build.side_effect = RuntimeError("failed to solve")
        with pytest.raises(RuntimeError, match="failed to solve"):
            async with jail(scratch):
                pass
        run.assert_not_called()

    def describe_the_proxy_container() -> None:
        async def it_runs_attached_on_the_default_bridge_as_its_pinned_user(
            scratch: Path, run: AsyncMock
        ) -> None:
            async with jail(scratch):
                options = started(run)
            assert options["interactive"]
            assert options["init"]
            assert options["image"] == "botbox-proxy:latest"
            assert options["network"] == ["bridge"]
            assert options["user"] == "100:101"
            assert options["pids_limit"] == "256"
            assert options["cap_drop"] == ["ALL"]
            assert options["security_opt"] == ["no-new-privileges"]

        async def it_is_named_and_labelled_with_the_run_token(
            scratch: Path, run: AsyncMock
        ) -> None:
            async with jail(scratch):
                options = started(run)
            assert options["name"] == PROXY
            assert options["label"] == f"botbox.run={TOKEN}"

        async def it_does_not_remove_itself(scratch: Path, run: AsyncMock) -> None:
            async with jail(scratch):
                [args] = run.call_args.args
            assert "--rm" not in args

        async def it_keeps_the_last_of_its_output_in_one_buffer(
            scratch: Path, run: AsyncMock
        ) -> None:
            async with jail(scratch):
                options = run.call_args.kwargs
            assert options["stdout"] is options["stderr"]
            assert isinstance(options["stdout"], bytearray)
            assert options["limit"] == OUTPUT_LIMIT == 64 * 1024

        async def it_waits_for_the_socket_with_the_client_and_its_output(
            scratch: Path, run: AsyncMock, wait: AsyncMock, steps: list[str]
        ) -> None:
            async with jail(scratch):
                steps.append("body")
            [socket, client, output, timeout] = wait.call_args.args
            assert socket == scratch / "sockets" / "proxy.sock"
            assert isinstance(client, asyncio.Future)
            assert output is run.call_args.kwargs["stdout"]
            assert timeout == 30
            assert steps.index("proxy up") < steps.index("body")

    def describe_the_mounts() -> None:
        async def it_mounts_the_filter_read_only(scratch: Path, run: AsyncMock) -> None:
            async with jail(scratch):
                mounts = volumes(run)
            assert mounts["/etc/tinyproxy/filter"] == (scratch / "filter", "ro")

        async def it_mounts_the_sockets_and_log_read_write(scratch: Path, run: AsyncMock) -> None:
            async with jail(scratch):
                mounts = volumes(run)
            assert mounts["/run/botbox"] == (scratch / "sockets", "rw")
            assert mounts["/var/log/tinyproxy"] == (scratch / "proxy", "rw")

        async def it_lets_the_proxy_user_create_the_socket(scratch: Path) -> None:
            async with jail(scratch):
                assert (scratch / "sockets").stat().st_mode & 0o777 == 0o777

        async def it_lets_the_proxy_user_read_the_filter_and_write_the_log(
            scratch: Path,
        ) -> None:
            async with jail(scratch):
                assert (scratch / "filter").stat().st_mode & 0o777 == 0o644
                assert (scratch / "proxy").stat().st_mode & 0o777 == 0o755
                assert (scratch / "proxy" / "tinyproxy.log").stat().st_mode & 0o777 == 0o666

    def describe_the_allowlist() -> None:
        async def it_admits_each_host_by_connect_on_443_and_plain_http_on_80(
            scratch: Path,
        ) -> None:
            async with jail(scratch, ("api.anthropic.com", "[::1]:8443")):
                pass
            assert (scratch / "filter").read_text() == (
                "^api\\.anthropic\\.com(:443)?$\n"
                "^http://api\\.anthropic\\.com(:80)?(/|$)\n"
                "^\\[::1\\]:8443(:443)?$\n"
                "^http://\\[::1\\]:8443(:80)?(/|$)\n"
            )

    def describe_the_lifetime_pipe() -> None:
        async def it_gives_the_proxy_the_read_end_and_holds_the_write_end_owner_only(
            scratch: Path, run: AsyncMock, os: MagicMock, owned: set[IO[bytes]]
        ) -> None:
            async with jail(scratch):
                assert len(owned) == 1
                assert run.call_args.kwargs["stdin"] == 3
                os.fdopen.assert_called_once_with(4, "wb")
                os.close.assert_not_called()
            assert not owned

        async def it_stops_the_proxy_with_its_client_stdin_name_and_grace(
            scratch: Path, stop: AsyncMock, owned: set[IO[bytes]]
        ) -> None:
            held: list[IO[bytes]] = []
            async with jail(scratch):
                held.extend(owned)
            [client, stdin, name, grace] = stop.call_args.args
            assert client.done()
            assert stdin is held[0]
            assert (name, grace) == (PROXY, 10)

        async def it_closes_the_read_end_on_the_way_out(scratch: Path, os: MagicMock) -> None:
            async with jail(scratch):
                pass
            os.close.assert_called_once_with(3)

    def describe_teardown() -> None:
        async def it_stops_the_proxy_under_settle_once_the_body_is_done(
            scratch: Path, steps: list[str]
        ) -> None:
            async with jail(scratch):
                steps.append("body")
            assert steps[-3:] == ["body", "settle", "proxy stopped"]

        async def it_stops_the_proxy_when_the_body_raises(scratch: Path, stop: AsyncMock) -> None:
            with pytest.raises(KeyError):
                async with jail(scratch):
                    raise KeyError
            stop.assert_awaited_once()

        async def it_stops_a_proxy_that_never_came_up(
            scratch: Path, wait: AsyncMock, stop: AsyncMock
        ) -> None:
            wait.side_effect = RuntimeError("botbox proxy did not start")
            with pytest.raises(RuntimeError, match="did not start"):
                async with jail(scratch):
                    pass
            stop.assert_awaited_once()

        async def it_still_closes_the_read_end_when_the_stop_raises(
            scratch: Path, stop: AsyncMock, os: MagicMock
        ) -> None:
            stop.side_effect = asyncio.CancelledError
            with pytest.raises(asyncio.CancelledError):
                async with jail(scratch):
                    pass
            os.close.assert_called_once_with(3)

    def describe_the_log() -> None:
        async def it_starts_empty(scratch: Path) -> None:
            async with jail(scratch) as net:
                assert net.log == ""

        async def it_reads_the_log_on_the_way_out(scratch: Path) -> None:
            async with jail(scratch) as net:
                (scratch / "proxy" / "tinyproxy.log").write_text(REFUSAL)
            assert net.log == REFUSAL

        async def it_reads_the_log_when_the_body_raises(scratch: Path) -> None:
            with pytest.raises(KeyError):
                async with jail(scratch) as net:
                    (scratch / "proxy" / "tinyproxy.log").write_text(REFUSAL)
                    raise KeyError
            assert net.log == REFUSAL

        async def it_reads_the_log_as_utf8_replacing_what_is_not(scratch: Path) -> None:
            async with jail(scratch) as net:
                (scratch / "proxy" / "tinyproxy.log").write_bytes("GET /café \xff\n".encode())
            assert net.log == "GET /café \ufffd\n"

        async def it_warns_and_keeps_an_empty_log_when_it_cannot_read_it(scratch: Path) -> None:
            with pytest.warns(RuntimeWarning, match="^botbox could not read its proxy log: "):
                async with jail(scratch) as net:
                    unreadable(scratch / "proxy" / "tinyproxy.log")
            assert net.log == ""

        async def it_keeps_the_bodys_error_when_it_cannot_read_the_log(scratch: Path) -> None:
            with (
                pytest.warns(RuntimeWarning, match="could not read its proxy log"),
                pytest.raises(KeyError),
            ):
                async with jail(scratch):
                    unreadable(scratch / "proxy" / "tinyproxy.log")
                    raise KeyError


def unreadable(log: Path) -> None:
    log.unlink()
    log.mkdir()
