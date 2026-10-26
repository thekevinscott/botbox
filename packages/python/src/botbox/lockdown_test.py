import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

import botbox.lockdown as lockdown_module
from botbox.lockdown import (
    CREDENTIAL_SOCKET_DIR,
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


@pytest.fixture
def served() -> asyncio.Event:
    """Set to let the proxy's attached client exit."""
    return asyncio.Event()


class Image:
    """The built proxy image: `run` starts an attached client that serves until `served`."""

    def __init__(self, served: asyncio.Event, steps: list[str]) -> None:
        self.served = served
        self.steps = steps
        self.command: tuple[str, ...] | None = None
        self.options: dict[str, Any] = {}
        self.container: Mock | None = None
        self.hangs = False
        self.refuses: BaseException | None = None

    async def run(self, *command: str, **options: Any) -> Mock:
        self.command, self.options = command, options
        self.steps.append("run proxy")
        if self.hangs:
            await asyncio.Event().wait()
        if self.refuses is not None:
            raise self.refuses

        async def attached() -> int:
            await self.served.wait()
            return 0

        client = asyncio.ensure_future(attached())

        async def wait() -> int:
            return await client

        self.container = Mock(client=client, stdin=Mock(), wait=wait)
        self.container.name = options["name"]
        return self.container


class Container:
    """A container wrapped by name, before its client starts."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.client = None
        self.stdin = None


@pytest.fixture(autouse=True)
def container() -> Iterator[None]:
    with patch("botbox.lockdown.Container", Container):
        yield


@pytest.fixture(autouse=True)
def image(served: asyncio.Event, steps: list[str]) -> Image:
    return Image(served, steps)


@pytest.fixture(autouse=True)
def dockerfile(steps: list[str], image: Image) -> Iterator[Mock]:
    async def built(tag: str) -> Image:
        steps.append(f"build {tag}")
        return image

    with patch("botbox.lockdown.Dockerfile", autospec=True) as m:
        m.return_value.build.side_effect = built
        yield m


@pytest.fixture
def build(dockerfile: Mock) -> AsyncMock:
    build: AsyncMock = dockerfile.return_value.build
    return build


@pytest.fixture
def volume_fails() -> dict[str, Exception]:
    """What `docker volume create` or `rm` raises, keyed by subcommand."""
    return {}


@pytest.fixture(autouse=True)
def docker_volume(steps: list[str], volume_fails: dict[str, Exception]) -> Iterator[None]:
    @asynccontextmanager
    async def volume(
        name: str, *, labels: dict[str, str], on_error: Callable[[Exception], None]
    ) -> AsyncIterator[Any]:
        steps.append(f"create {name} {labels}")
        if "create" in volume_fails:
            raise volume_fails["create"]
        try:
            socket = Mock(mount=lambda target: (name, target, "rw"))
            socket.name = name
            yield socket
        finally:
            if "rm" in volume_fails:
                on_error(volume_fails["rm"])
            else:
                steps.append(f"remove {name}")

    with patch("botbox.lockdown.Volume", volume):
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
    async def stopped(proxy: Mock, *_args: object) -> None:
        served.set()
        if proxy.client is not None:
            await proxy.wait()
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


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    path = tmp_path / "scratch"
    path.mkdir()
    return path


def jail(scratch: Path, allow: tuple[str, ...] = ALLOW, output: Path | None = None) -> Any:
    return lockdown(allow, scratch, TOKEN, output)


def allowlist(image: Image) -> str:
    return str(image.options["env"]["BOTBOX_FILTER"])


LABELS = {"botbox.run": TOKEN}


def describe_lockdown() -> None:
    async def it_requires_injection_and_secret_together(scratch: Path) -> None:
        injection: Any = object()  # Passed only to the mocked sidecar.
        with pytest.raises(ValueError, match="injection and secret"):
            async with lockdown(ALLOW, scratch, TOKEN, injection=injection):
                pass
        with pytest.raises(ValueError, match="injection and secret"):
            async with lockdown(ALLOW, scratch, TOKEN, secret="Bearer fake"):
                pass

    async def it_starts_credentials_after_tinyproxy_and_mounts_the_socket(
        scratch: Path, steps: list[str]
    ) -> None:
        injection: Any = object()  # Passed only to the mocked sidecar.

        @asynccontextmanager
        async def sidecar(*_args: object, **_kwargs: object) -> AsyncIterator[Mock]:
            steps.append("credentials up")
            try:
                yield Mock()
            finally:
                steps.append("credentials stopped")

        with patch("botbox.lockdown.credential_proxy", side_effect=sidecar) as start:
            async with lockdown(
                ALLOW, scratch, TOKEN, injection=injection, secret="Bearer fake"
            ) as net:
                steps.append("body")
                assert net.credentials is not None
                assert net.credential_mount is not None
                assert net.credential_mount.source == str(scratch / "credential-sockets")
                assert net.credential_mount.target == CREDENTIAL_SOCKET_DIR
                assert net.credential_mount.read_only
            start.assert_called_once_with(
                injection,
                "Bearer fake",
                proxy=net.proxy,
                sockets=scratch / "credential-sockets",
                token=TOKEN,
                log=scratch / "credentials.log",
            )
        assert steps.index("proxy up") < steps.index("credentials up") < steps.index("body")
        assert steps.index("credentials stopped") < steps.index("proxy stopped")

    async def it_yields_what_a_locked_down_container_needs(scratch: Path, image: Image) -> None:
        async with jail(scratch) as net:
            assert net.proxy is image.container
            assert image.container is not None
            assert image.container.name == PROXY
            assert net.volume.name == VOLUME
            url = "http://127.0.0.1:41893"
            assert net.envs == {
                "HTTP_PROXY": url,
                "HTTPS_PROXY": url,
                "http_proxy": url,
                "https_proxy": url,
                "NO_PROXY": "localhost,127.0.0.1",
            }

    async def it_builds_the_shipped_proxy_first(
        scratch: Path, dockerfile: Mock, build: AsyncMock, steps: list[str]
    ) -> None:
        async with jail(scratch):
            pass
        [file] = dockerfile.call_args.args
        assert file == PROXY_DIR / "Dockerfile"
        build.assert_awaited_once_with("botbox-proxy:latest")
        assert (file.parent / "tinyproxy.conf").exists()
        assert steps[0] == "build botbox-proxy:latest"
        assert "run proxy" in steps

    async def it_starts_nothing_when_the_build_fails(
        scratch: Path, build: AsyncMock, image: Image
    ) -> None:
        build.side_effect = RuntimeError("failed to solve")
        with pytest.raises(RuntimeError, match="failed to solve"):
            async with jail(scratch):
                pass
        assert image.command is None

    async def it_names_resources_per_run(tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        async with (
            lockdown(ALLOW, tmp_path / "a", "aaaaaaaaaaaa") as first,
            lockdown(ALLOW, tmp_path / "b", "bbbbbbbbbbbb") as second,
        ):
            assert first.proxy.name != second.proxy.name
            assert first.volume.name != second.volume.name

    def describe_the_proxy_container() -> None:
        async def it_runs_attached_on_the_default_bridge_as_its_pinned_user(
            scratch: Path, image: Image
        ) -> None:
            async with jail(scratch):
                pass
            options = dict(image.options)
            assert image.command == ()
            assert options.pop("stdin") == asyncio.subprocess.PIPE
            assert options.pop("stdout") is options.pop("stderr")
            options.pop("env")
            options.pop("mounts")
            assert options == {
                "name": PROXY,
                "labels": LABELS,
                "init": True,
                "user": "100:101",
                "network": "bridge",
                "pids_limit": 256,
                "log_driver": "none",
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges"],
            }

        async def it_sends_all_its_output_to_the_log_in_scratch(
            scratch: Path, image: Image
        ) -> None:
            async with jail(scratch):
                image.options["stdout"](REFUSAL.encode())
                assert (scratch / "proxy.log").read_text() == REFUSAL

        async def it_waits_for_the_proxy_with_the_client_and_its_output(
            scratch: Path, wait: AsyncMock, image: Image, steps: list[str]
        ) -> None:
            async with jail(scratch):
                steps.append("body")
            [client, output, timeout] = wait.call_args.args
            assert image.container is not None
            assert client is image.container.client
            assert output == scratch / "proxy.log"
            assert timeout == 30
            assert steps.index("proxy up") < steps.index("body")

        async def it_starts_nothing_when_the_log_will_not_open(
            tmp_path: Path, image: Image
        ) -> None:
            with pytest.raises(FileNotFoundError):
                async with jail(tmp_path / "missing"):
                    pass
            assert image.command is None

        async def it_stops_the_proxy_with_its_grace(
            scratch: Path, image: Image, stop: AsyncMock
        ) -> None:
            async with jail(scratch):
                pass
            proxy: Mock
            [proxy, grace] = stop.call_args.args
            assert proxy is image.container
            assert grace == 10
            assert await proxy.wait() == 0

        async def it_removes_a_proxy_whose_start_was_cancelled(
            scratch: Path, image: Image, stop: AsyncMock, steps: list[str]
        ) -> None:
            image.hangs = True

            async def held() -> None:
                async with jail(scratch):
                    pass

            task = asyncio.create_task(held())
            while "run proxy" not in steps:
                await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            [proxy, _] = stop.call_args.args
            assert (proxy.name, proxy.client) == (PROXY, None)
            assert steps[-2:] == ["proxy stopped", f"remove {VOLUME}"]

        async def it_removes_a_proxy_that_would_not_start(
            scratch: Path, image: Image, stop: AsyncMock
        ) -> None:
            image.refuses = RuntimeError("name in use")
            with pytest.raises(RuntimeError, match="name in use"):
                async with jail(scratch):
                    pass
            [proxy, _] = stop.call_args.args
            assert proxy.name == PROXY

    def describe_the_volume() -> None:
        async def it_mounts_only_the_runs_volume_read_write(scratch: Path, image: Image) -> None:
            async with jail(scratch):
                pass
            assert image.options["mounts"] == [(VOLUME, "/run/botbox", "rw")]

        async def it_creates_it_labelled_before_the_proxy_starts(
            scratch: Path, steps: list[str]
        ) -> None:
            async with jail(scratch):
                pass
            assert steps.index(f"create {VOLUME} {LABELS}") < steps.index("run proxy")

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
            scratch: Path, image: Image, volume_fails: dict[str, Exception]
        ) -> None:
            volume_fails["create"] = RuntimeError("no space")
            with pytest.raises(RuntimeError, match="no space"):
                async with jail(scratch):
                    pass
            assert image.command is None

        async def it_warns_when_it_cannot_be_removed(
            scratch: Path, volume_fails: dict[str, Exception]
        ) -> None:
            volume_fails["rm"] = RuntimeError("volume is in use")
            match = f"^botbox could not remove its volume {VOLUME}: volume is in use$"
            with pytest.warns(RuntimeWarning, match=match) as warned:
                async with jail(scratch):
                    pass
            assert warned[0].filename == lockdown_module.__file__

    def describe_the_allowlist() -> None:
        async def it_admits_each_host_by_connect_on_443_and_plain_http_on_80(
            scratch: Path, image: Image
        ) -> None:
            async with jail(scratch, ("api.anthropic.com", "[::1]:8443")):
                pass
            assert allowlist(image) == (
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
            scratch: Path, image: Image, host: str, authority: str
        ) -> None:
            """tinyproxy reads each line as a case-insensitive ERE; they read the same in `re`."""
            async with jail(scratch, (host,)):
                pass
            patterns = allowlist(image).splitlines()

            def admitted(url: str) -> bool:
                return any(re.search(p, url, re.IGNORECASE) for p in patterns)

            assert admitted(f"{authority}:443")
            assert admitted(f"http://{authority}/")
            assert admitted(f"http://{authority}:80/")
            assert not admitted(f"{authority}:8022")
            assert not admitted(f"http://{authority}:8022/")

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

        async def it_still_removes_the_volume_when_the_stop_raises(
            scratch: Path, stop: AsyncMock, steps: list[str]
        ) -> None:
            stop.side_effect = asyncio.CancelledError
            with pytest.raises(asyncio.CancelledError):
                async with jail(scratch):
                    pass
            assert steps[-1] == f"remove {VOLUME}"

    def describe_with_output() -> None:
        async def it_writes_the_log_into_output_too(
            scratch: Path, tmp_path: Path, image: Image
        ) -> None:
            output = tmp_path / "output"
            output.mkdir()
            async with jail(scratch, output=output):
                image.options["stdout"](REFUSAL.encode())
            assert (output / "proxy.log").read_text() == REFUSAL
            assert (scratch / "proxy.log").read_text() == REFUSAL

        async def it_truncates_a_previous_log(scratch: Path, tmp_path: Path) -> None:
            output = tmp_path / "output"
            output.mkdir()
            (output / "proxy.log").write_text(REFUSAL)
            async with jail(scratch, output=output):
                assert (output / "proxy.log").read_bytes() == b""

        async def it_warns_and_carries_on_without_an_output_it_cannot_open(
            scratch: Path, tmp_path: Path, steps: list[str]
        ) -> None:
            with pytest.warns(RuntimeWarning, match="stopped writing to"):
                async with jail(scratch, output=tmp_path / "missing"):
                    steps.append("body")
            assert "body" in steps


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
