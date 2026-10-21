import re
import subprocess
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

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
REFUSAL = 'NOTICE Proxying refused on filtered domain "github.com"\n'

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


def serve(docker: MagicMock) -> None:
    """What the proxy does once started: put its socket in the directory it was given."""
    [sockets] = [
        s for s, t, _ in docker.container.create.call_args.kwargs["volumes"] if t == SOCKET_DIR
    ]
    (Path(sockets) / "proxy.sock").touch()


@pytest.fixture
def popen(docker: MagicMock, proxy: Mock) -> Iterator[MagicMock]:
    def start(_argv: list[str], **_options: object) -> Mock:
        serve(docker)
        return proxy

    with patch("botbox.lockdown.subprocess.Popen", autospec=True) as m:
        m.side_effect = start
        yield m


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def jail(docker: MagicMock, popen: MagicMock, scratch: Path) -> Jail:  # noqa: ARG001
    def call(allow: tuple[str, ...] = ALLOW) -> AbstractContextManager[Lockdown]:
        return lockdown(allow, scratch)

    return call


def created(docker: MagicMock) -> dict[str, object]:
    options: dict[str, object] = docker.container.create.call_args.kwargs
    return options


def proxy_name(docker: MagicMock) -> str:
    name = created(docker)["name"]
    assert isinstance(name, str)
    return name


def volumes(docker: MagicMock) -> dict[str, tuple[Path, str]]:
    return {t: (Path(s), m) for s, t, m in docker.container.create.call_args.kwargs["volumes"]}


def describe_lockdown() -> None:
    def it_names_the_proxy_container_per_run(jail: Jail, docker: MagicMock) -> None:
        with jail() as net:
            assert re.fullmatch(r"botbox-proxy-[0-9a-f]{12}", net.proxy)
            assert net.proxy == proxy_name(docker)

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

        def it_puts_the_proxy_on_the_default_bridge_only(jail: Jail, docker: MagicMock) -> None:
            with jail():
                assert created(docker)["networks"] == ["bridge"]

    def describe_the_socket_directory() -> None:
        def it_lives_in_the_scratch_directory(jail: Jail, scratch: Path) -> None:
            with jail() as net:
                assert net.sockets == scratch / "sockets"

        def it_lets_the_proxy_user_create_the_socket(jail: Jail, scratch: Path) -> None:
            with jail():
                assert (scratch / "sockets").stat().st_mode & 0o777 == 0o777

        def it_is_mounted_into_the_proxy_read_write(
            jail: Jail, docker: MagicMock, scratch: Path
        ) -> None:
            with jail():
                assert volumes(docker)[SOCKET_DIR] == (scratch / "sockets", "rw")

    def describe_the_proxy_container() -> None:
        def it_creates_it_from_the_image_it_built(jail: Jail, docker: MagicMock) -> None:
            with jail():
                assert docker.container.create.call_args.args == (
                    docker.build.call_args.kwargs["tags"],
                )

        def it_holds_stdin_open_and_removes_itself_on_exit(jail: Jail, docker: MagicMock) -> None:
            with jail():
                assert created(docker)["interactive"] is True
                assert created(docker)["remove"] is True

        def it_runs_a_real_init_so_its_exit_ends_the_pid_namespace(
            jail: Jail, docker: MagicMock
        ) -> None:
            with jail():
                assert created(docker)["init"] is True

        def it_caps_the_processes_each_connection_forks(jail: Jail, docker: MagicMock) -> None:
            with jail():
                assert created(docker)["pids_limit"] == 256

        def it_attaches_with_the_owner_holding_its_stdin(
            jail: Jail, docker: MagicMock, popen: MagicMock
        ) -> None:
            with jail():
                [argv] = popen.call_args.args
                assert argv == ["docker", "start", "--attach", "--interactive", proxy_name(docker)]
                assert popen.call_args.kwargs["stdin"] == subprocess.PIPE
                assert popen.call_args.kwargs["stderr"] == subprocess.STDOUT

        def it_creates_before_it_attaches(jail: Jail, docker: MagicMock, popen: MagicMock) -> None:
            steps: list[str] = []
            docker.container.create.side_effect = lambda *_a, **_k: steps.append("create")
            start = popen.side_effect
            popen.side_effect = lambda *a, **k: (steps.append("start"), start(*a, **k))[1]
            with jail():
                assert steps == ["create", "start"]

        def it_yields_once_the_socket_is_up(jail: Jail, scratch: Path) -> None:
            with jail():
                assert (scratch / "sockets" / "proxy.sock").exists()

        def it_raises_with_the_proxys_output_when_it_exits_before_the_socket(
            jail: Jail, popen: MagicMock, proxy: Mock, scratch: Path
        ) -> None:
            def start(_argv: list[str], **options: object) -> Mock:
                stdout = options["stdout"]
                assert hasattr(stdout, "write")
                stdout.write("tinyproxy: bad config\n")
                stdout.flush()
                return proxy

            popen.side_effect = start
            proxy.poll.return_value = 1
            with pytest.raises(RuntimeError, match="tinyproxy: bad config"), jail():
                pass
            assert not (scratch / "sockets" / "proxy.sock").exists()

        def it_raises_when_the_socket_never_appears(
            jail: Jail, popen: MagicMock, proxy: Mock
        ) -> None:
            popen.side_effect = lambda *_a, **_k: proxy
            clock = iter(range(0, 1000, 10))
            with (
                patch("botbox.lockdown.time.monotonic", side_effect=lambda: next(clock)),
                patch("botbox.lockdown.time.sleep"),
                pytest.raises(RuntimeError, match="proxy"),
                jail(),
            ):
                pass

    def describe_the_proxy_config() -> None:
        def it_is_the_shipped_one_baked_into_the_image(jail: Jail, docker: MagicMock) -> None:
            with jail():
                assert "/etc/tinyproxy/tinyproxy.conf" not in volumes(docker)
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
        def it_anchors_each_host(jail: Jail, docker: MagicMock) -> None:
            with jail(allow=("api.anthropic.com", "example.test")):
                source, mode = volumes(docker)["/etc/tinyproxy/filter"]
                assert source.read_text() == "^api\\.anthropic\\.com$\n^example\\.test$\n"
                assert mode == "ro"

        def it_is_readable_by_the_proxy_user(jail: Jail, docker: MagicMock) -> None:
            with jail():
                source, _ = volumes(docker)["/etc/tinyproxy/filter"]
                assert source.stat().st_mode & 0o777 == 0o644

        def it_lives_in_the_scratch_directory(jail: Jail, docker: MagicMock, scratch: Path) -> None:
            with jail():
                assert volumes(docker)["/etc/tinyproxy/filter"][0] == scratch / "filter"

    def describe_the_log() -> None:
        def it_mounts_a_scratch_directory_where_tinyproxy_logs(
            jail: Jail, docker: MagicMock, scratch: Path
        ) -> None:
            with jail():
                assert volumes(docker)["/var/log/tinyproxy"] == (scratch / "proxy", "rw")

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
            jail: Jail, docker: MagicMock
        ) -> None:
            with jail():
                assert created(docker)["cap_drop"] == ["ALL"]

        def it_starts_the_proxy_with_privilege_escalation_forbidden(
            jail: Jail, docker: MagicMock
        ) -> None:
            with jail():
                assert created(docker)["security_options"] == ["no-new-privileges"]

    def describe_teardown() -> None:
        def it_ends_the_proxys_stdin_and_waits_for_it(jail: Jail, proxy: Mock) -> None:
            with jail():
                proxy.stdin.close.assert_not_called()
            proxy.stdin.close.assert_called_once_with()
            proxy.wait.assert_called_once()

        def it_removes_the_proxy_by_name(jail: Jail, docker: MagicMock) -> None:
            with jail():
                docker.container.remove.assert_not_called()
            docker.container.remove.assert_called_once_with(proxy_name(docker), force=True)

        def it_removes_after_the_proxy_exits(jail: Jail, docker: MagicMock, proxy: Mock) -> None:
            manager = Mock()
            manager.attach_mock(proxy.wait, "wait")
            manager.attach_mock(docker.container.remove, "remove")
            with jail():
                pass
            assert [c[0] for c in manager.mock_calls] == ["wait", "remove"]

        def it_kills_the_attach_when_the_proxy_wont_exit(
            jail: Jail, docker: MagicMock, proxy: Mock
        ) -> None:
            proxy.wait.side_effect = [subprocess.TimeoutExpired("docker", 10), 0]
            with jail():
                pass
            proxy.kill.assert_called_once_with()
            docker.container.remove.assert_called_once_with(proxy_name(docker), force=True)

        def it_tears_down_when_the_body_raises(jail: Jail, docker: MagicMock, proxy: Mock) -> None:
            with pytest.raises(RuntimeError, match="boom"), jail():
                raise RuntimeError("boom")
            proxy.stdin.close.assert_called_once_with()
            docker.container.remove.assert_called_once()

        def it_removes_a_proxy_whose_create_was_interrupted(
            jail: Jail, docker: MagicMock, popen: MagicMock
        ) -> None:
            docker.container.create.side_effect = KeyboardInterrupt
            with pytest.raises(KeyboardInterrupt), jail():
                pass
            popen.assert_not_called()
            docker.container.remove.assert_called_once_with(proxy_name(docker), force=True)

        def it_removes_the_proxy_when_attaching_fails(
            jail: Jail, docker: MagicMock, popen: MagicMock
        ) -> None:
            popen.side_effect = OSError("no docker")
            with pytest.raises(OSError, match="no docker"), jail():
                pass
            docker.container.remove.assert_called_once_with(proxy_name(docker), force=True)

        def it_swallows_a_failed_removal(jail: Jail, docker: MagicMock) -> None:
            docker.container.remove.side_effect = DockerException("gone")
            with jail():
                pass

        def it_swallows_a_closed_pipe(jail: Jail, proxy: Mock) -> None:
            proxy.stdin.close.side_effect = BrokenPipeError
            with jail():
                pass
            proxy.wait.assert_called_once()

        def it_propagates_the_body_error_over_a_teardown_error(
            jail: Jail, docker: MagicMock
        ) -> None:
            docker.container.remove.side_effect = DockerException("gone")
            with pytest.raises(ValueError, match="body boom"), jail():
                raise ValueError("body boom")

        def it_waits_with_a_bound(jail: Jail, proxy: Mock) -> None:
            with jail():
                pass
            assert proxy.wait.call_args_list == [call(timeout=10)]
