import re
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from botbox.lockdown import Lockdown, lockdown


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
        m.run.return_value = "proxy-container"
        m.network.docker_cmd = ["docker"]
        yield m


@pytest.fixture
def docker_cli() -> Iterator[MagicMock]:
    with patch("botbox.lockdown.docker_utils", autospec=True) as m:
        yield m.run


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def jail(docker: MagicMock, docker_cli: MagicMock, scratch: Path) -> Jail:  # noqa: ARG001
    def call(allow: tuple[str, ...] = ALLOW) -> AbstractContextManager[Lockdown]:
        return lockdown(allow, scratch)

    return call


def volumes(docker: MagicMock) -> dict[str, tuple[Path, str]]:
    return {t: (Path(s), m) for s, t, m in docker.run.call_args.kwargs["volumes"]}


def describe_lockdown() -> None:
    def it_yields_the_internal_network(jail: Jail) -> None:
        with jail() as net:
            assert re.fullmatch(r"botbox-jail-[0-9a-f]{12}", net.network)

    def it_points_the_proxy_env_at_the_sidecar(jail: Jail, docker: MagicMock) -> None:
        with jail() as net:
            name = docker.run.call_args.kwargs["name"]
            assert name.startswith("botbox-proxy-")
            url = f"http://{name}:8888"
            assert net.envs == {
                "HTTP_PROXY": url,
                "HTTPS_PROXY": url,
                "http_proxy": url,
                "https_proxy": url,
                "NO_PROXY": "localhost,127.0.0.1",
            }

    @pytest.mark.usefixtures("docker", "docker_cli")
    def it_names_resources_per_run(tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        with lockdown(ALLOW, tmp_path / "a") as first, lockdown(ALLOW, tmp_path / "b") as second:
            assert first.network != second.network

    def describe_the_network() -> None:
        def it_creates_the_jail_network_internal(jail: Jail, docker_cli: MagicMock) -> None:
            with jail() as net:
                pass
            [argv] = docker_cli.call_args.args
            assert argv == ["docker", "network", "create", "--internal", net.network]

        def it_creates_a_separate_egress_network_for_the_proxy(
            jail: Jail, docker: MagicMock
        ) -> None:
            with jail():
                [egress] = docker.network.create.call_args.args
            assert egress.startswith("botbox-egress-")

        def it_puts_the_proxy_on_both(jail: Jail, docker: MagicMock) -> None:
            with jail() as net:
                assert docker.run.call_args.kwargs["networks"] == [
                    docker.network.create.call_args.args[0]
                ]
                docker.network.connect.assert_called_once_with(net.network, "proxy-container")

        def it_runs_the_proxy_detached(jail: Jail, docker: MagicMock) -> None:
            with jail():
                assert docker.run.call_args.kwargs["detach"] is True

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
            gone = DockerException("gone")
            docker.container.remove.side_effect = gone
            docker.network.disconnect.side_effect = gone
            docker.network.remove.side_effect = gone
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

        def it_runs_the_image_it_built(jail: Jail, docker: MagicMock) -> None:
            with jail():
                assert docker.run.call_args.args == (docker.build.call_args.kwargs["tags"],)

    def describe_hardening() -> None:
        def it_starts_the_proxy_with_the_capability_set_dropped(
            jail: Jail, docker: MagicMock
        ) -> None:
            with jail():
                assert docker.run.call_args.kwargs["cap_drop"] == ["ALL"]

        def it_starts_the_proxy_with_privilege_escalation_forbidden(
            jail: Jail, docker: MagicMock
        ) -> None:
            with jail():
                assert docker.run.call_args.kwargs["security_options"] == ["no-new-privileges"]

    def describe_teardown() -> None:
        def it_removes_the_proxy_and_both_networks(jail: Jail, docker: MagicMock) -> None:
            with jail() as net:
                docker.container.remove.assert_not_called()
            docker.container.remove.assert_called_once_with("proxy-container", force=True)
            [egress] = docker.network.create.call_args.args
            removed = [call.args[0] for call in docker.network.remove.call_args_list]
            assert removed == [net.network, egress]

        def it_tears_down_when_the_body_raises(jail: Jail, docker: MagicMock) -> None:
            with pytest.raises(RuntimeError), jail():
                raise RuntimeError("boom")
            docker.container.remove.assert_called_once()
            assert docker.network.remove.call_count == 2

        def it_removes_nothing_that_was_never_created(jail: Jail, docker: MagicMock) -> None:
            docker.network.create.side_effect = DockerException("gone")
            with pytest.raises(DockerException), jail():
                pass
            docker.container.remove.assert_not_called()
            docker.network.disconnect.assert_not_called()
            assert docker.network.remove.call_count == 1

        def it_removes_both_networks_even_when_the_proxy_removal_fails(
            jail: Jail, docker: MagicMock
        ) -> None:
            docker.container.remove.side_effect = DockerException("gone")
            with jail():
                pass
            assert docker.network.remove.call_count == 2

        def it_removes_the_second_network_when_the_first_removal_fails(
            jail: Jail, docker: MagicMock
        ) -> None:
            docker.network.remove.side_effect = [DockerException("gone"), None]
            with jail():
                pass
            assert docker.network.remove.call_count == 2

        def it_frees_a_network_whose_proxy_outlived_its_removal(
            jail: Jail, docker: MagicMock
        ) -> None:
            """A live endpoint pins its network, so the endpoint is detached first."""
            docker.container.remove.side_effect = DockerException("gone")
            with jail() as net:
                pass
            [egress] = docker.network.create.call_args.args
            steps = [
                (name, args[0])
                for name, args, _ in docker.mock_calls
                if name in {"network.disconnect", "network.remove"}
            ]
            assert steps == [
                ("network.disconnect", net.network),
                ("network.remove", net.network),
                ("network.disconnect", egress),
                ("network.remove", egress),
            ]
            assert docker.network.disconnect.call_args.args[1] == "proxy-container"
            assert docker.network.disconnect.call_args.kwargs == {"force": True}

        def it_keeps_detaching_when_a_disconnect_fails(jail: Jail, docker: MagicMock) -> None:
            docker.container.remove.side_effect = DockerException("gone")
            docker.network.disconnect.side_effect = DockerException("gone")
            with jail():
                pass
            assert docker.network.disconnect.call_count == 2
            assert docker.network.remove.call_count == 2

        def it_disconnects_nothing_when_the_proxy_was_removed(
            jail: Jail, docker: MagicMock
        ) -> None:
            with jail():
                pass
            docker.network.disconnect.assert_not_called()

        def it_disconnects_nothing_when_the_proxy_never_started(
            jail: Jail, docker: MagicMock
        ) -> None:
            docker.run.side_effect = DockerException("no such image")
            with pytest.raises(DockerException), jail():
                pass
            docker.container.remove.assert_not_called()
            docker.network.disconnect.assert_not_called()
            assert docker.network.remove.call_count == 2

        def it_propagates_the_body_error_over_a_teardown_error(
            jail: Jail, docker: MagicMock
        ) -> None:
            docker.container.remove.side_effect = DockerException("gone")
            with pytest.raises(ValueError, match="body boom"), jail():
                raise ValueError("body boom")
            assert docker.network.remove.call_count == 2
