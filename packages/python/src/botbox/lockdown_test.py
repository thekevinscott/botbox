import argparse
import asyncio
import re
from collections.abc import Awaitable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

import botbox.lockdown as lockdown_module
from botbox.lockdown import (
    PROXY_CONF,
    PROXY_DIR,
    RELAY_DIR,
    RELAY_PORT,
    lockdown,
)

ALLOW = ("api.anthropic.com",)
REFUSAL = 'NOTICE Proxying refused on filtered url "github.com:443"\n'
TOKEN = "0123456789ab"
PROXY = "botbox-proxy-0123456789ab"
VOLUME = "botbox-run-0123456789ab"


@pytest.fixture
def steps() -> list[str]:
    return []


@pytest.fixture(autouse=True)
def build(steps: list[str]) -> Iterator[AsyncMock]:
    async def built(_context: Path, *, tag: str, **_options: Any) -> None:
        steps.append(f"build {tag}")

    with patch("botbox.lockdown.build", autospec=True, side_effect=built) as m:
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

    with patch("botbox.lockdown.run", autospec=True, side_effect=attached) as m:
        yield m


@pytest.fixture
def volume_fails() -> dict[str, BaseException]:
    """What `docker volume create` or `rm` raises, keyed by subcommand."""
    return {}


@pytest.fixture(autouse=True)
def docker_volume(steps: list[str], volume_fails: dict[str, BaseException]) -> Iterator[None]:
    """The real `adocker.volume` over a fake `docker volume`."""

    async def docker(*args: str) -> str:
        if args[1] == "create":
            steps.append(f"create {args[-1]} {args[-2]}")
        if args[1] in volume_fails:
            raise volume_fails[args[1]]
        if args[1] == "rm":
            steps.append(f"remove {args[-1]}")
        return ""

    with (
        patch("adocker.volume.run_docker", side_effect=docker),
        patch("adocker.remove_volume.run_docker", side_effect=docker),
    ):
        yield


@pytest.fixture(autouse=True)
def wait(steps: list[str]) -> Iterator[AsyncMock]:
    async def up(*_args: object) -> None:
        await asyncio.sleep(0)
        steps.append("proxy up")

    with patch("botbox.lockdown.wait_for_proxy", autospec=True, side_effect=up) as m:
        yield m


@pytest.fixture(autouse=True)
def stop(served: asyncio.Event, steps: list[str]) -> Iterator[AsyncMock]:
    async def stopped(client: asyncio.Future[int], stdin: IO[bytes], *_args: object) -> None:
        stdin.close()
        served.set()
        await client
        steps.append("proxy stopped")

    with patch("botbox.lockdown.stop_proxy", autospec=True, side_effect=stopped) as m:
        yield m


@pytest.fixture(autouse=True)
def settle(steps: list[str]) -> Iterator[AsyncMock]:
    async def settled(step: Awaitable[None]) -> None:
        steps.append("settle")
        await step

    with patch("botbox.lockdown.settle", autospec=True, side_effect=settled) as m:
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

    with patch("botbox.lockdown.owner_only", owner_only):
        yield pipes


@pytest.fixture(autouse=True)
def os() -> Iterator[MagicMock]:
    with patch("botbox.lockdown.os", autospec=True) as m:
        m.pipe.return_value = (3, 4)
        m.fdopen.side_effect = lambda _fd, _mode: Mock()
        yield m


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    return tmp_path


def jail(scratch: Path, allow: tuple[str, ...] = ALLOW, output: Path | None = None) -> Any:
    return lockdown(allow, scratch, TOKEN, output)


RUN = argparse.ArgumentParser()
for flag in ("--interactive", "--init"):
    RUN.add_argument(flag, action="store_true")
for flag in ("--name", "--user", "--pids-limit", "--label", "--log-driver"):
    RUN.add_argument(flag)
for flag in ("--network", "--cap-drop", "--security-opt", "--volume", "--env"):
    RUN.add_argument(flag, action="append", default=[])
RUN.add_argument("image")


def started(run: AsyncMock) -> dict[str, Any]:
    """The options of the proxy's `docker run`; an unexpected flag fails the parse."""
    [args] = run.call_args.args
    return vars(RUN.parse_args(args))


def volumes(run: AsyncMock) -> dict[str, tuple[str, str]]:
    mounts = (volume.split(":") for volume in started(run)["volume"])
    return {target: (source, mode) for source, target, mode in mounts}


def allowlist(run: AsyncMock) -> str:
    [env] = started(run)["env"]
    return str(env).removeprefix("BOTBOX_FILTER=")


def describe_lockdown() -> None:
    async def it_yields_what_a_locked_down_container_needs(scratch: Path) -> None:
        async with jail(scratch) as net:
            assert net.proxy == PROXY
            assert net.volume == VOLUME
            url = "http://127.0.0.1:41893"
            assert net.envs == {
                "HTTP_PROXY": url,
                "HTTPS_PROXY": url,
                "http_proxy": url,
                "https_proxy": url,
                "NO_PROXY": "localhost,127.0.0.1",
            }

    async def it_builds_the_shipped_proxy_first(
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
        assert steps[0] == "build botbox-proxy:latest"
        assert "run proxy" in steps

    async def it_starts_nothing_when_the_build_fails(
        scratch: Path, build: AsyncMock, run: AsyncMock
    ) -> None:
        build.side_effect = RuntimeError("failed to solve")
        with pytest.raises(RuntimeError, match="failed to solve"):
            async with jail(scratch):
                pass
        run.assert_not_called()

    async def it_names_resources_per_run(tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        async with (
            lockdown(ALLOW, tmp_path / "a", "aaaaaaaaaaaa") as first,
            lockdown(ALLOW, tmp_path / "b", "bbbbbbbbbbbb") as second,
        ):
            assert first.proxy != second.proxy
            assert first.volume != second.volume

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
            assert options["log_driver"] == "none"
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

        async def it_sends_all_its_output_to_one_log_file_it_closes(
            scratch: Path, run: AsyncMock
        ) -> None:
            async with jail(scratch):
                options = run.call_args.kwargs
                assert options["stdout"] is options["stderr"]
                assert options["stdout"].name == str(scratch / "proxy.log")
                assert "limit" not in options
            assert options["stdout"].closed

        async def it_waits_for_the_proxy_with_the_client_and_its_output(
            scratch: Path, wait: AsyncMock, steps: list[str]
        ) -> None:
            async with jail(scratch):
                steps.append("body")
            [client, output, timeout] = wait.call_args.args
            assert isinstance(client, asyncio.Future)
            assert output == scratch / "proxy.log"
            assert timeout == 30
            assert steps.index("proxy up") < steps.index("body")

    def describe_the_volume() -> None:
        async def it_mounts_only_the_runs_volume_read_write(scratch: Path, run: AsyncMock) -> None:
            async with jail(scratch):
                mounts = volumes(run)
            assert mounts == {"/run/botbox": (VOLUME, "rw")}

        async def it_creates_it_labelled_before_the_proxy_starts(
            scratch: Path, steps: list[str]
        ) -> None:
            async with jail(scratch):
                pass
            assert steps.index(f"create {VOLUME} botbox.run={TOKEN}") < steps.index("run proxy")

        async def it_removes_it_once_the_proxy_is_stopped(scratch: Path, steps: list[str]) -> None:
            async with jail(scratch):
                pass
            assert steps[-2:] == ["proxy stopped", f"remove {VOLUME}"]

        async def it_removes_it_when_the_proxy_never_came_up(
            scratch: Path, wait: AsyncMock, steps: list[str]
        ) -> None:
            wait.side_effect = RuntimeError("botbox proxy did not start")
            with pytest.raises(RuntimeError, match="did not start"):
                async with jail(scratch):
                    pass
            assert steps[-1] == f"remove {VOLUME}"

        async def it_starts_nothing_when_it_cannot_be_created(
            scratch: Path, run: AsyncMock, volume_fails: dict[str, BaseException]
        ) -> None:
            volume_fails["create"] = RuntimeError("no space")
            with pytest.raises(RuntimeError, match="no space"):
                async with jail(scratch):
                    pass
            run.assert_not_called()

        async def it_warns_when_it_cannot_be_removed(
            scratch: Path, volume_fails: dict[str, BaseException]
        ) -> None:
            volume_fails["rm"] = RuntimeError("volume is in use")
            match = f"^botbox could not remove its volume {VOLUME}: volume is in use$"
            with pytest.warns(RuntimeWarning, match=match) as warned:
                async with jail(scratch):
                    pass
            assert warned[0].filename == lockdown_module.__file__

    def describe_the_allowlist() -> None:
        async def it_admits_each_host_by_connect_on_443_and_plain_http_on_80(
            scratch: Path, run: AsyncMock
        ) -> None:
            async with jail(scratch, ("api.anthropic.com", "[::1]:8443")):
                pass
            assert allowlist(run) == (
                "^api\\.anthropic\\.com(:443)?$\n"
                "^http://api\\.anthropic\\.com(:80)?(/|$)\n"
                "^\\[::1\\]:8443(:443)?$\n"
                "^http://\\[::1\\]:8443(:80)?(/|$)\n"
            )

        @pytest.mark.parametrize(
            ("host", "authority"),
            [
                ("2001:db8::1", "[2001:db8::1]"),
                ("192.0.2.1", "192.0.2.1"),
                ("api.anthropic.com", "api.anthropic.com"),
            ],
        )
        async def it_matches_the_urls_tinyproxy_filters_only_on_443_and_80(
            scratch: Path, run: AsyncMock, host: str, authority: str
        ) -> None:
            """tinyproxy reads each line as a case-insensitive ERE; they read the same in `re`."""
            async with jail(scratch, (host,)):
                pass
            patterns = allowlist(run).splitlines()

            def admitted(url: str) -> bool:
                return any(re.search(p, url, re.IGNORECASE) for p in patterns)

            assert admitted(f"{authority}:443")
            assert admitted(f"http://{authority}/")
            assert admitted(f"http://{authority}:80/")
            assert not admitted(f"{authority}:8022")
            assert not admitted(f"http://{authority}:8022/")

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

        async def it_closes_both_ends_when_the_log_will_not_open(
            tmp_path: Path, scratch: Path, run: AsyncMock, os: MagicMock
        ) -> None:
            os.fdopen.side_effect = None
            os.fdopen.return_value.close.side_effect = OSError("flush failed")
            with pytest.raises(FileNotFoundError):
                async with jail(scratch, output=tmp_path / "missing"):
                    pass
            run.assert_not_called()
            os.fdopen.return_value.close.assert_called_once_with()
            os.close.assert_called_once_with(3)

    def describe_teardown() -> None:
        async def it_stops_the_proxy_under_settle_once_the_body_is_done(
            scratch: Path, steps: list[str]
        ) -> None:
            async with jail(scratch):
                steps.append("body")
            assert steps[-4:-1] == ["body", "settle", "proxy stopped"]

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
                (scratch / "proxy.log").write_text(REFUSAL)
            assert net.log == REFUSAL

        async def it_reads_the_log_when_the_body_raises(scratch: Path) -> None:
            with pytest.raises(KeyError):
                async with jail(scratch) as net:
                    (scratch / "proxy.log").write_text(REFUSAL)
                    raise KeyError
            assert net.log == REFUSAL

        async def it_reads_the_log_as_utf8_replacing_what_is_not(scratch: Path) -> None:
            async with jail(scratch) as net:
                (scratch / "proxy.log").write_bytes("GET /café ".encode() + b"\xff\n")
            assert net.log == "GET /café \ufffd\n"

        async def it_warns_and_keeps_an_empty_log_when_it_cannot_read_it(scratch: Path) -> None:
            with pytest.warns(RuntimeWarning, match="^botbox could not read its proxy log: ") as w:
                async with jail(scratch) as net:
                    unreadable(scratch / "proxy.log")
            assert net.log == ""
            assert w[0].filename == __file__

        async def it_keeps_the_bodys_error_when_it_cannot_read_the_log(scratch: Path) -> None:
            with (
                pytest.warns(RuntimeWarning, match="could not read its proxy log"),
                pytest.raises(KeyError),
            ):
                async with jail(scratch):
                    unreadable(scratch / "proxy.log")
                    raise KeyError

    def describe_with_output() -> None:
        async def it_writes_the_log_into_output_and_reads_nothing_back(
            scratch: Path, tmp_path: Path, run: AsyncMock
        ) -> None:
            output = tmp_path / "output"
            output.mkdir()
            async with jail(scratch, output=output) as net:
                run.call_args.kwargs["stdout"].write(REFUSAL.encode())
            assert net.log == ""
            assert (output / "proxy.log").read_text() == REFUSAL
            assert not (scratch / "proxy.log").exists()

        async def it_truncates_a_previous_log(scratch: Path, tmp_path: Path) -> None:
            output = tmp_path / "output"
            output.mkdir()
            (output / "proxy.log").write_text(REFUSAL)
            async with jail(scratch, output=output):
                assert (output / "proxy.log").read_bytes() == b""


def unreadable(log: Path) -> None:
    log.unlink()
    log.mkdir()


def describe_the_shipped_proxy() -> None:
    def it_relays_on_an_uncommon_port() -> None:
        assert RELAY_PORT not in {3128, 8080, 8888}
        assert 1024 < RELAY_PORT < 49152

    def it_bakes_its_config_into_the_image_rather_than_mounting_it() -> None:
        assert (PROXY_DIR / "tinyproxy.conf") == PROXY_CONF
        assert "COPY tinyproxy.conf" in (PROXY_DIR / "Dockerfile").read_text()

    def it_listens_on_loopback_only() -> None:
        conf = PROXY_CONF.read_text()
        assert re.findall(r"^Listen .*$", conf, re.M) == ["Listen 127.0.0.1"]

    def it_admits_only_loopback_clients() -> None:
        conf = PROXY_CONF.read_text()
        assert re.findall(r"^Allow .*$", conf, re.M) == ["Allow 127.0.0.1"]

    def it_logs_to_its_attached_output_rather_than_a_file() -> None:
        conf = PROXY_CONF.read_text()
        assert re.findall(r"^LogFile", conf, re.M) == []
        assert "tinyproxy -d " in (PROXY_DIR / "botbox-proxy").read_text()

    def it_denies_by_default() -> None:
        assert "FilterDefaultDeny Yes" in PROXY_CONF.read_text()

    def it_filters_the_whole_url_so_the_port_is_checked() -> None:
        assert "FilterURLs Yes" in PROXY_CONF.read_text()

    def it_caps_the_proxy_sides_children() -> None:
        script = (PROXY_DIR / "botbox-proxy").read_text()
        assert "max-children=" in script
        assert "UNIX-LISTEN:/run/botbox/proxy.sock" in script

    def it_gives_the_socket_directory_to_the_proxy_user_for_the_volume_to_copy() -> None:
        assert (
            "install -d -o tinyproxy -g tinyproxy -m 0755 /run/botbox"
            in (PROXY_DIR / "Dockerfile").read_text()
        )

    def it_says_it_is_listening_once_its_socket_exists() -> None:
        script = (PROXY_DIR / "botbox-proxy").read_text()
        assert "until [ -S /run/botbox/proxy.sock ]" in script
        assert 'echo "botbox-proxy: listening"' in script

    def it_writes_its_filter_from_the_environment() -> None:
        script = (PROXY_DIR / "botbox-proxy").read_text()
        assert "printf '%s' \"$BOTBOX_FILTER\" >/etc/tinyproxy/filter" in script
        assert 'Filter "/etc/tinyproxy/filter"' in PROXY_CONF.read_text()

    def it_listens_in_the_box_on_the_relay_port() -> None:
        script = (RELAY_DIR / "botbox-relay").read_text()
        assert f"TCP-LISTEN:{RELAY_PORT},bind=127.0.0.1" in script
        assert f":{RELAY_PORT:04X} 00000000:0000 0A" in script
        assert "UNIX-CONNECT:/run/botbox/proxy.sock" in script
