import argparse
import os
import re
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import IO, Any
from unittest.mock import ANY, MagicMock, Mock, patch

import pytest

from botbox.lockdown import (
    PROXY_CONF,
    PROXY_DIR,
    RELAY_DIR,
    RELAY_PORT,
    SOCKET_DIR,
    Lockdown,
    lockdown,
)


class DockerException(Exception):
    """Stands in for python_on_whales' DockerException."""


@pytest.fixture(autouse=True)
def docker_exception() -> Iterator[None]:
    with patch("botbox.lockdown.DockerException", DockerException):
        yield


ALLOW = ("api.anthropic.com",)
REFUSAL = 'NOTICE Proxying refused on filtered url "github.com:443"\n'

type Jail = Callable[..., AbstractContextManager[Lockdown]]


@pytest.fixture
def docker() -> Iterator[MagicMock]:
    with patch("botbox.lockdown.docker", autospec=True) as m:
        yield m


@pytest.fixture
def proxy() -> Mock:
    """The attached `docker start` of the proxy: it serves until its stdin closes."""
    process = Mock(stdin=Mock())
    process.poll.return_value = None
    process.wait.return_value = 0
    return process


@pytest.fixture
def subprocess(proxy: Mock) -> Iterator[MagicMock]:
    with patch("botbox.lockdown.subprocess") as m:
        m.Popen.return_value = proxy
        yield m


@pytest.fixture
def popen(subprocess: MagicMock) -> MagicMock:
    popen: MagicMock = subprocess.Popen
    return popen


@pytest.fixture
def wait() -> Iterator[MagicMock]:
    with patch("botbox.lockdown.wait_for_socket", autospec=True) as m:
        yield m


@pytest.fixture
def stop() -> Iterator[MagicMock]:
    with patch("botbox.lockdown.stop_attached", autospec=True) as m:
        m.side_effect = lambda _process, stdin, _timeout: stdin.close()
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


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def jail(
    docker: MagicMock,  # noqa: ARG001
    popen: MagicMock,  # noqa: ARG001
    wait: MagicMock,  # noqa: ARG001
    stop: MagicMock,  # noqa: ARG001
    scratch: Path,
) -> Jail:
    def call(allow: tuple[str, ...] = ALLOW) -> AbstractContextManager[Lockdown]:
        return lockdown(allow, scratch)

    return call


RUN = argparse.ArgumentParser()
for flag in ("--interactive", "--rm", "--init"):
    RUN.add_argument(flag, action="store_true")
for flag in ("--name", "--user", "--pids-limit"):
    RUN.add_argument(flag)
for flag in ("--network", "--cap-drop", "--security-opt", "--volume"):
    RUN.add_argument(flag, action="append", default=[])
RUN.add_argument("image")
RUN.add_argument("command", nargs="*")


def started(popen: MagicMock) -> dict[str, Any]:
    """The options of the proxy's `docker run`; an unexpected flag fails the parse."""
    [argv] = popen.call_args.args
    assert argv[:2] == ["docker", "run"]
    return vars(RUN.parse_args(argv[2:]))


def proxy_name(popen: MagicMock) -> str:
    name = started(popen)["name"]
    assert isinstance(name, str)
    return name


def volumes(popen: MagicMock) -> dict[str, tuple[Path, str]]:
    mounts = (v.split(":") for v in started(popen)["volume"])
    return {t: (Path(s), m) for s, t, m in mounts}


def describe_lockdown() -> None:
    def it_names_the_proxy_container_per_run(jail: Jail, popen: MagicMock) -> None:
        with jail() as net:
            assert re.fullmatch(r"botbox-proxy-[0-9a-f]{12}", net.proxy)
            assert net.proxy == proxy_name(popen)

    def it_points_the_proxy_env_at_the_in_box_relay(jail: Jail) -> None:
        url = f"http://127.0.0.1:{RELAY_PORT}"
        with jail() as net:
            assert net.envs == {
                "HTTP_PROXY": url,
                "HTTPS_PROXY": url,
                "http_proxy": url,
                "https_proxy": url,
                "NO_PROXY": "localhost,127.0.0.1",
            }

    def it_relays_on_an_uncommon_port(jail: Jail) -> None:
        with jail():
            assert RELAY_PORT not in {3128, 8080, 8888}
            assert 1024 < RELAY_PORT < 49152

    @pytest.mark.usefixtures("popen")
    @pytest.mark.usefixtures("docker", "popen", "wait", "stop")
    def it_names_resources_per_run(tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        with lockdown(ALLOW, tmp_path / "a") as first, lockdown(ALLOW, tmp_path / "b") as second:
            assert first.proxy != second.proxy
            assert first.sockets != second.sockets

    def describe_the_network() -> None:
        def it_creates_no_network(jail: Jail, docker: MagicMock) -> None:
            with jail():
                pass
            assert docker.network.mock_calls == []

        def it_puts_the_proxy_on_the_default_bridge_only(jail: Jail, popen: MagicMock) -> None:
            with jail():
                assert started(popen)["network"] == ["bridge"]

    def describe_the_socket_directory() -> None:
        def it_lives_in_the_scratch_directory(jail: Jail, scratch: Path) -> None:
            with jail() as net:
                assert net.sockets == scratch / "sockets"

        def it_lets_the_proxy_user_create_the_socket(jail: Jail, scratch: Path) -> None:
            with jail():
                assert (scratch / "sockets").stat().st_mode & 0o777 == 0o777

        def it_is_mounted_into_the_proxy_read_write(
            jail: Jail, popen: MagicMock, scratch: Path
        ) -> None:
            with jail():
                assert volumes(popen)[SOCKET_DIR] == (scratch / "sockets", "rw")

    def describe_the_proxy_container() -> None:
        def it_runs_the_image_it_built_with_its_own_command(
            jail: Jail, docker: MagicMock, popen: MagicMock
        ) -> None:
            with jail():
                assert started(popen)["image"] == docker.build.call_args.kwargs["tags"]
                assert started(popen)["command"] == []

        def it_holds_stdin_open_and_removes_itself_on_exit(jail: Jail, popen: MagicMock) -> None:
            with jail():
                assert started(popen)["interactive"] is True
                assert started(popen)["rm"] is True

        def it_runs_a_real_init_so_its_exit_ends_the_pid_namespace(
            jail: Jail, popen: MagicMock
        ) -> None:
            with jail():
                assert started(popen)["init"] is True

        def it_runs_as_a_pinned_uid_apart_from_the_agents(jail: Jail, popen: MagicMock) -> None:
            with jail():
                assert started(popen)["user"] == "100:101"

        def it_caps_the_processes_each_connection_forks(jail: Jail, popen: MagicMock) -> None:
            with jail():
                assert started(popen)["pids_limit"] == "256"

        def it_sends_the_proxys_errors_with_its_output(jail: Jail, subprocess: MagicMock) -> None:
            with jail():
                assert subprocess.Popen.call_args.kwargs["stderr"] is subprocess.STDOUT

        def it_sends_the_proxys_output_to_the_scratch_directory(
            jail: Jail, popen: MagicMock, scratch: Path
        ) -> None:
            with jail():
                assert popen.call_args.kwargs["stdout"].name == str(scratch / "proxy.out")

        def it_never_creates_a_container_that_nothing_starts(jail: Jail, docker: MagicMock) -> None:
            with jail():
                pass
            docker.container.create.assert_not_called()

        def it_waits_for_the_socket_before_yielding(
            jail: Jail, wait: MagicMock, proxy: Mock, scratch: Path
        ) -> None:
            with jail():
                wait.assert_called_once_with(
                    scratch / "sockets" / "proxy.sock", proxy, scratch / "proxy.out", 30
                )

        def it_stops_and_removes_a_proxy_that_never_came_up(
            jail: Jail,
            docker: MagicMock,
            wait: MagicMock,
            stop: MagicMock,
            proxy: Mock,
        ) -> None:
            wait.side_effect = RuntimeError("botbox proxy did not start")
            with pytest.raises(RuntimeError, match="did not start"), jail():
                pass
            stop.assert_called_once_with(proxy, ANY, 10)
            docker.container.remove.assert_called_once()

    def describe_the_lifetime_pipe() -> None:
        """The proxy's stdin: only this process may hold its write end, from start to close."""

        def it_holds_the_write_end_owner_only_before_the_proxy_starts(
            jail: Jail, popen: MagicMock, proxy: Mock, owned: set[IO[bytes]]
        ) -> None:
            def start(_argv: list[str], *, stdin: int, **_options: object) -> Mock:
                [held] = owned
                held.write(b"x")
                held.flush()
                assert os.read(stdin, 1) == b"x"
                return proxy

            popen.side_effect = start
            with jail():
                pass
            popen.assert_called_once()

        def it_keeps_holding_it_while_the_body_runs(jail: Jail, owned: set[IO[bytes]]) -> None:
            with jail():
                [held] = owned
                assert not held.closed

        def it_closes_it_before_letting_go(
            jail: Jail, stop: MagicMock, owned: set[IO[bytes]]
        ) -> None:
            def close(_process: Mock, stdin: IO[bytes], _timeout: float) -> None:
                assert {stdin} == owned
                stdin.close()

            stop.side_effect = close
            with jail():
                pass
            stop.assert_called_once()
            assert not owned

        def it_closes_the_read_end_once_the_proxy_has_it(jail: Jail, popen: MagicMock) -> None:
            with jail(), pytest.raises(OSError):
                os.fstat(popen.call_args.kwargs["stdin"])

        def it_closes_both_ends_when_the_start_fails(
            jail: Jail, popen: MagicMock, owned: set[IO[bytes]]
        ) -> None:
            pipes: list[tuple[int, IO[bytes]]] = []

            def start(_argv: list[str], *, stdin: int, **_options: object) -> Mock:
                pipes.append((stdin, next(iter(owned))))
                raise OSError("no docker")

            popen.side_effect = start
            with pytest.raises(OSError, match="no docker"), jail():
                pass
            [(read, held)] = pipes
            assert held.closed
            with pytest.raises(OSError):
                os.fstat(read)
            assert not owned

    def describe_the_proxy_config() -> None:
        def it_is_the_shipped_one_baked_into_the_image(jail: Jail, popen: MagicMock) -> None:
            with jail():
                assert "/etc/tinyproxy/tinyproxy.conf" not in volumes(popen)
            assert (PROXY_DIR / "tinyproxy.conf") == PROXY_CONF

        def it_listens_on_loopback_only(jail: Jail) -> None:
            with jail():
                pass
            conf = PROXY_CONF.read_text()
            assert re.findall(r"^Listen .*$", conf, re.M) == ["Listen 127.0.0.1"]

        def it_admits_only_loopback_clients(jail: Jail) -> None:
            with jail():
                pass
            conf = PROXY_CONF.read_text()
            assert re.findall(r"^Allow .*$", conf, re.M) == ["Allow 127.0.0.1"]

        def it_denies_by_default(jail: Jail) -> None:
            with jail():
                pass
            assert "FilterDefaultDeny Yes" in PROXY_CONF.read_text()

        def it_filters_the_whole_url_so_the_port_is_checked(jail: Jail) -> None:
            with jail():
                pass
            assert "FilterURLs Yes" in PROXY_CONF.read_text()

    def describe_the_relays() -> None:
        def it_caps_the_proxy_sides_children(jail: Jail) -> None:
            with jail():
                pass
            script = (PROXY_DIR / "botbox-proxy").read_text()
            assert "max-children=" in script
            assert "UNIX-LISTEN:/run/botbox/proxy.sock" in script

        def it_listens_in_the_box_on_the_relay_port(jail: Jail) -> None:
            with jail():
                pass
            script = (RELAY_DIR / "botbox-relay").read_text()
            assert f"TCP-LISTEN:{RELAY_PORT},bind=127.0.0.1" in script
            assert f":{RELAY_PORT:04X} 00000000:0000 0A" in script
            assert "UNIX-CONNECT:/run/botbox/proxy.sock" in script

    def describe_the_allowlist() -> None:
        def it_admits_each_host_by_connect_on_443_and_plain_http_on_80(
            jail: Jail, popen: MagicMock
        ) -> None:
            with jail(allow=("api.anthropic.com", "example.test")):
                source, mode = volumes(popen)["/etc/tinyproxy/filter"]
                assert source.read_text() == (
                    "^api\\.anthropic\\.com(:443)?$\n"
                    "^http://api\\.anthropic\\.com(:80)?(/|$)\n"
                    "^example\\.test(:443)?$\n"
                    "^http://example\\.test(:80)?(/|$)\n"
                )
                assert mode == "ro"

        def it_is_readable_by_the_proxy_user(jail: Jail, popen: MagicMock) -> None:
            with jail():
                source, _ = volumes(popen)["/etc/tinyproxy/filter"]
                assert source.stat().st_mode & 0o777 == 0o644

        def it_lives_in_the_scratch_directory(jail: Jail, popen: MagicMock, scratch: Path) -> None:
            with jail():
                assert volumes(popen)["/etc/tinyproxy/filter"][0] == scratch / "filter"

    def describe_the_log() -> None:
        def it_mounts_a_scratch_directory_where_tinyproxy_logs(
            jail: Jail, popen: MagicMock, scratch: Path
        ) -> None:
            with jail():
                assert volumes(popen)["/var/log/tinyproxy"] == (scratch / "proxy", "rw")

        def it_lets_the_proxy_user_into_the_directory(jail: Jail, scratch: Path) -> None:
            with jail():
                assert (scratch / "proxy").stat().st_mode & 0o777 == 0o755

        def it_lets_the_proxy_user_write_the_log(jail: Jail, scratch: Path) -> None:
            with jail():
                log = scratch / "proxy" / "tinyproxy.log"
                assert log.read_text() == ""
                assert log.stat().st_mode & 0o777 == 0o666

        def it_starts_empty(jail: Jail) -> None:
            with jail() as net:
                assert net.log == ""

        def it_reads_the_log_on_the_way_out(jail: Jail, scratch: Path) -> None:
            with jail() as net:
                (scratch / "proxy" / "tinyproxy.log").write_text(REFUSAL)
            assert net.log == REFUSAL

        def it_reads_the_log_when_the_body_raises(jail: Jail, scratch: Path) -> None:
            with pytest.raises(KeyboardInterrupt), jail() as net:
                (scratch / "proxy" / "tinyproxy.log").write_text(REFUSAL)
                raise KeyboardInterrupt
            assert net.log == REFUSAL

        def it_reads_the_log_when_the_daemon_is_gone(
            jail: Jail, docker: MagicMock, scratch: Path
        ) -> None:
            docker.container.remove.side_effect = DockerException("gone")
            with jail() as net:
                (scratch / "proxy" / "tinyproxy.log").write_text(REFUSAL)
            assert net.log == REFUSAL

    def describe_the_image() -> None:
        def it_builds_the_shipped_proxy_quietly(jail: Jail, docker: MagicMock) -> None:
            with jail():
                pass
            [context] = docker.build.call_args.args
            assert context == Path(docker.build.call_args.kwargs["file"]).parent
            assert (context / "tinyproxy.conf").exists()
            assert docker.build.call_args.kwargs["tags"] == "botbox-proxy:latest"
            assert docker.build.call_args.kwargs["progress"] is False

    def describe_hardening() -> None:
        def it_starts_the_proxy_with_the_capability_set_dropped(
            jail: Jail, popen: MagicMock
        ) -> None:
            with jail():
                assert started(popen)["cap_drop"] == ["ALL"]

        def it_starts_the_proxy_with_privilege_escalation_forbidden(
            jail: Jail, popen: MagicMock
        ) -> None:
            with jail():
                assert started(popen)["security_opt"] == ["no-new-privileges"]

    def describe_teardown() -> None:
        def it_stops_the_proxy_on_the_way_out(jail: Jail, stop: MagicMock, proxy: Mock) -> None:
            with jail():
                stop.assert_not_called()
            stop.assert_called_once_with(proxy, ANY, 10)

        def it_removes_the_proxy_by_name(jail: Jail, docker: MagicMock, popen: MagicMock) -> None:
            with jail():
                docker.container.remove.assert_not_called()
            docker.container.remove.assert_called_once_with(proxy_name(popen), force=True)

        def it_removes_after_the_proxy_stops(
            jail: Jail, docker: MagicMock, stop: MagicMock
        ) -> None:
            manager = Mock()
            manager.attach_mock(stop, "stop")
            manager.attach_mock(docker.container.remove, "remove")
            with jail():
                pass
            assert [c[0] for c in manager.mock_calls] == ["stop", "remove"]

        def it_tears_down_when_the_body_raises(
            jail: Jail, docker: MagicMock, stop: MagicMock, proxy: Mock
        ) -> None:
            with pytest.raises(RuntimeError, match="boom"), jail():
                raise RuntimeError("boom")
            stop.assert_called_once_with(proxy, ANY, 10)
            docker.container.remove.assert_called_once()

        def it_removes_a_proxy_whose_start_was_interrupted(
            jail: Jail, docker: MagicMock, popen: MagicMock
        ) -> None:
            popen.side_effect = KeyboardInterrupt
            with pytest.raises(KeyboardInterrupt), jail():
                pass
            docker.container.remove.assert_called_once_with(proxy_name(popen), force=True)

        def it_removes_the_proxy_when_attaching_fails(
            jail: Jail, docker: MagicMock, popen: MagicMock
        ) -> None:
            popen.side_effect = OSError("no docker")
            with pytest.raises(OSError, match="no docker"), jail():
                pass
            docker.container.remove.assert_called_once_with(proxy_name(popen), force=True)

        def it_swallows_a_failed_removal(jail: Jail, docker: MagicMock) -> None:
            docker.container.remove.side_effect = DockerException("gone")
            with jail():
                pass

        def it_propagates_the_body_error_over_a_teardown_error(
            jail: Jail, docker: MagicMock
        ) -> None:
            docker.container.remove.side_effect = DockerException("gone")
            with pytest.raises(ValueError, match="body boom"), jail():
                raise ValueError("body boom")
