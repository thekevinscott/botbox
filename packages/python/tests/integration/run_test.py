import contextlib
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from conftest import Daemon
from python_on_whales.exceptions import DockerException

from botbox import Botbox, ClaudeAgent, RunResult

CREDENTIALS = '{"claudeAiOauth": {"accessToken": "t"}}'
REFUSAL = 'NOTICE Proxying refused on filtered domain "github.com"\n'


@pytest.fixture
def claude_home(tmp_path: Path) -> Path:
    home = tmp_path / "claude-home"
    home.mkdir()
    (home / ".credentials.json").write_text(CREDENTIALS)
    return home


@pytest.fixture
def agent(claude_home: Path) -> ClaudeAgent:
    return ClaudeAgent(host_home=claude_home)


@pytest.fixture
def box(agent: ClaudeAgent) -> Botbox:
    return Botbox(agent)


@pytest.fixture
def work(tmp_path: Path) -> Path:
    directory = tmp_path / "work"
    directory.mkdir()
    return directory


@pytest.fixture
def tests(tmp_path: Path) -> Path:
    directory = tmp_path / "tests"
    directory.mkdir()
    (directory / "a_test.py").write_text("def test_a(): pass\n")
    return directory


@pytest.fixture
def in_tmp_path(tmp_path: Path) -> Iterator[None]:
    with contextlib.chdir(tmp_path):
        yield


@pytest.fixture
def claude_writes_a_transcript(daemon: Daemon) -> None:
    def container(home: Path, proxy_log: Path) -> None:
        session = home / ".claude" / "projects" / "-work"
        session.mkdir(parents=True)
        (session / "abc.jsonl").write_text('{"type": "user"}\n')
        (home / ".claude" / "settings.json").write_text("{}")
        with proxy_log.open("a") as log:
            log.write(REFUSAL)

    daemon.container = container


def volume(call: dict[str, Any], target: str) -> tuple[str, str]:
    [(source, mode)] = [(s, m) for s, t, m in call["volumes"] if t == target]
    return source, mode


def describe_run() -> None:
    def describe_the_result() -> None:
        def it_returns_a_run_result(box: Botbox) -> None:
            assert isinstance(box.run("true"), RunResult)

        def it_separates_stdout_from_stderr(box: Botbox, daemon: Daemon) -> None:
            daemon.logs = [("stdout", b"one\n"), ("stderr", b"warn\n"), ("stdout", b"two\n")]
            result = box.run("true")
            assert (result.stdout, result.stderr) == ("one\ntwo\n", "warn\n")

        def it_reports_the_exit_code(box: Botbox) -> None:
            assert box.run("true").exit_code == 0

        def it_returns_a_non_zero_exit_as_a_normal_result(box: Botbox, daemon: Daemon) -> None:
            daemon.logs = [("stderr", b"API error\n")]
            daemon.exit_code = 3
            result = box.run("false")
            assert (result.exit_code, result.stderr) == (3, "API error\n")

        def it_is_empty_when_the_command_says_nothing(box: Botbox) -> None:
            result = box.run("true")
            assert (result.stdout, result.stderr, result.transcript, result.proxy) == (
                "",
                "",
                {},
                "",
            )

    def describe_the_command() -> None:
        def it_runs_the_command_through_sh(box: Botbox, daemon: Daemon) -> None:
            box.run('claude -p "Fix the tests" --output-format json')
            assert daemon.agent["command"] == [
                "sh",
                "-c",
                'claude -p "Fix the tests" --output-format json',
            ]

        def it_runs_the_agents_image(box: Botbox, daemon: Daemon) -> None:
            box.run("true")
            assert daemon.agent["image"] == "botbox-claude:latest"

        def it_runs_the_callers_layer_when_there_is_one(
            agent: ClaudeAgent, daemon: Daemon, tmp_path: Path
        ) -> None:
            layer = tmp_path / "Dockerfile"
            layer.write_text("FROM botbox-claude:latest\n")
            box = Botbox(agent, dockerfile=layer)
            box.run("true")
            assert daemon.agent["image"] == box.build()
            assert daemon.agent["image"] != "botbox-claude:latest"

        def it_runs_as_the_node_user(box: Botbox, daemon: Daemon) -> None:
            box.run("true")
            assert daemon.agent["user"] == "node"

    def describe_the_build() -> None:
        def it_builds_the_agent_image_then_the_proxy_every_run(
            box: Botbox, builds: list[dict[str, Any]]
        ) -> None:
            box.run("true")
            box.run("true")
            assert [b["tags"] for b in builds] == [
                "botbox-claude:latest",
                "botbox-proxy:latest",
            ] * 2

        def it_builds_the_shipped_proxy_image(box: Botbox, builds: list[dict[str, Any]]) -> None:
            box.run("true")
            proxy = builds[1]
            assert proxy["context"] == proxy["file"].parent
            assert proxy["text"].startswith("FROM alpine:")

        def it_starts_nothing_when_the_build_fails(
            box: Botbox, docker_build: MagicMock, docker: dict[str, MagicMock]
        ) -> None:
            docker_build.side_effect = RuntimeError("build failed")
            with pytest.raises(RuntimeError, match="build failed"):
                box.run("true")
            docker["run"].assert_not_called()
            docker["cli"].assert_not_called()
            docker["network"].create.assert_not_called()

    def describe_lockdown() -> None:
        def it_drops_every_capability(box: Botbox, daemon: Daemon) -> None:
            box.run("true")
            assert daemon.agent["cap_drop"] == ["ALL"]

        def it_forbids_privilege_escalation(box: Botbox, daemon: Daemon) -> None:
            box.run("true")
            assert daemon.agent["security_options"] == ["no-new-privileges"]

        def it_hardens_the_proxy_too(box: Botbox, daemon: Daemon) -> None:
            box.run("true")
            assert daemon.proxy["cap_drop"] == ["ALL"]
            assert daemon.proxy["security_options"] == ["no-new-privileges"]

    def describe_the_network() -> None:
        def it_puts_the_agent_on_a_fresh_internal_network(
            box: Botbox, daemon: Daemon, docker: dict[str, MagicMock]
        ) -> None:
            box.run("true")
            [network] = daemon.agent["networks"]
            assert re.fullmatch(r"botbox-jail-[0-9a-f]{12}", network)
            [argv] = docker["cli"].call_args.args
            assert argv == ["docker", "network", "create", "--internal", network]

        def it_puts_the_proxy_on_an_egress_network_and_the_agents(
            box: Botbox, daemon: Daemon, docker: dict[str, MagicMock]
        ) -> None:
            box.run("true")
            [egress] = docker["network"].create.call_args.args
            assert re.fullmatch(r"botbox-egress-[0-9a-f]{12}", egress)
            assert daemon.proxy["networks"] == [egress]
            docker["network"].connect.assert_called_once_with(
                daemon.agent["networks"][0], "proxy-container"
            )

        def it_uses_new_networks_each_run(box: Botbox, daemon: Daemon) -> None:
            box.run("true")
            box.run("true")
            assert daemon.runs[1]["networks"] != daemon.runs[3]["networks"]

        def it_points_every_proxy_variable_at_the_sidecar(box: Botbox, daemon: Daemon) -> None:
            box.run("true")
            name = daemon.proxy["name"]
            assert re.fullmatch(r"botbox-proxy-[0-9a-f]{12}", name)
            url = f"http://{name}:8888"
            assert daemon.agent["envs"] == {
                "HTTP_PROXY": url,
                "HTTPS_PROXY": url,
                "http_proxy": url,
                "https_proxy": url,
                "NO_PROXY": "localhost,127.0.0.1",
            }

        def it_runs_the_proxy_detached(box: Botbox, daemon: Daemon) -> None:
            box.run("true")
            assert daemon.proxy["detach"] is True

    def describe_an_api_key() -> None:
        @pytest.fixture
        def keyed(claude_home: Path) -> Botbox:
            return Botbox(ClaudeAgent(api_key="sk-test", host_home=claude_home))

        def it_stages_the_key_and_its_helper_instead_of_the_credentials(
            keyed: Botbox, daemon: Daemon
        ) -> None:
            keyed.run("true")
            files = daemon.agent["files"]["/home/node"]
            assert files == {
                ".claude/api_key": "sk-test",
                ".claude/settings.json": '{"apiKeyHelper": "cat /home/node/.claude/api_key"}',
            }

        def it_keeps_the_key_out_of_the_container_create_call(
            keyed: Botbox, daemon: Daemon
        ) -> None:
            keyed.run("true")
            call = {k: v for k, v in daemon.agent.items() if k != "files"}
            assert "sk-test" not in repr(call)
            assert "sk-test" not in repr(daemon.proxy)

    def describe_the_allowlist() -> None:
        def it_admits_the_agents_hosts(box: Botbox, daemon: Daemon) -> None:
            box.run("true")
            assert daemon.proxy["files"]["/etc/tinyproxy/filter"] == {
                ".": "^api\\.anthropic\\.com$\n"
            }

        def it_adds_the_callers_hosts(agent: ClaudeAgent, daemon: Daemon) -> None:
            Botbox(agent, allow=["registry.npmjs.org"]).run("true")
            assert daemon.proxy["files"]["/etc/tinyproxy/filter"] == {
                ".": "^api\\.anthropic\\.com$\n^registry\\.npmjs\\.org$\n"
            }

        def it_mounts_the_filter_read_only_and_readable_by_the_proxy_user(
            box: Botbox, daemon: Daemon
        ) -> None:
            box.run("true")
            assert volume(daemon.proxy, "/etc/tinyproxy/filter")[1] == "ro"
            assert daemon.proxy["modes"]["/etc/tinyproxy/filter"] & 0o044 == 0o044

    def describe_the_home() -> None:
        def it_mounts_a_temporary_home_at_the_agents_home(
            box: Botbox, daemon: Daemon, claude_home: Path
        ) -> None:
            box.run("true")
            source, mode = volume(daemon.agent, "/home/node")
            assert mode == "rw"
            assert Path(source) != claude_home
            assert Path(source).is_absolute()

        def it_stages_the_credentials_before_the_command_starts(
            box: Botbox, daemon: Daemon
        ) -> None:
            box.run("true")
            assert daemon.agent["files"]["/home/node"] == {".claude/.credentials.json": CREDENTIALS}

        def it_uses_a_fresh_home_each_run(box: Botbox, daemon: Daemon) -> None:
            box.run("true")
            box.run("true")
            assert volume(daemon.runs[1], "/home/node") != volume(daemon.runs[3], "/home/node")

        def it_deletes_the_home_afterwards(box: Botbox, daemon: Daemon) -> None:
            box.run("true")
            assert not Path(volume(daemon.agent, "/home/node")[0]).exists()

        def it_deletes_the_proxy_log_directory_afterwards(box: Botbox, daemon: Daemon) -> None:
            box.run("true")
            assert not Path(volume(daemon.proxy, "/var/log/tinyproxy")[0]).exists()

        def it_raises_before_any_container_without_credentials(
            box: Botbox, claude_home: Path, docker: dict[str, MagicMock]
        ) -> None:
            (claude_home / ".credentials.json").unlink()
            with pytest.raises(FileNotFoundError, match=r"\.credentials\.json"):
                box.run("true")
            docker["run"].assert_not_called()
            docker["cli"].assert_not_called()

        def it_starts_the_command_in_the_home_by_default(box: Botbox, daemon: Daemon) -> None:
            box.run("true")
            assert daemon.agent["workdir"] == "/home/node"

    def describe_mounts() -> None:
        def it_bind_mounts_each_host_path_with_its_mode(
            box: Botbox, daemon: Daemon, tests: Path, work: Path
        ) -> None:
            box.run("true", mounts=[(tests, "/tests", "ro"), (work, "/work", "rw")])
            assert volume(daemon.agent, "/tests") == (str(tests), "ro")
            assert volume(daemon.agent, "/work") == (str(work), "rw")

        def it_mounts_the_host_directory_itself(box: Botbox, daemon: Daemon, tests: Path) -> None:
            box.run("true", mounts=[(tests, "/tests", "ro")])
            assert daemon.agent["files"]["/tests"] == {"a_test.py": "def test_a(): pass\n"}

        @pytest.mark.usefixtures("in_tmp_path")
        def it_resolves_relative_host_paths_against_the_working_directory(
            box: Botbox, daemon: Daemon, tests: Path
        ) -> None:
            box.run("true", mounts=[("./tests", "/tests", "ro")])
            assert volume(daemon.agent, "/tests") == (str(tests), "ro")

        def it_accepts_paths_as_strings(box: Botbox, daemon: Daemon, work: Path) -> None:
            box.run("true", mounts=[(str(work), "/work", "rw")])
            assert volume(daemon.agent, "/work") == (str(work), "rw")

        def it_accepts_a_container_path_as_a_path(box: Botbox, daemon: Daemon, work: Path) -> None:
            box.run("true", mounts=[(work, Path("/work"), "rw")])
            assert volume(daemon.agent, "/work") == (str(work), "rw")

        def it_mounts_a_single_file(box: Botbox, daemon: Daemon, tests: Path) -> None:
            box.run("true", mounts=[(tests / "a_test.py", "/a_test.py", "ro")])
            assert volume(daemon.agent, "/a_test.py") == (str(tests / "a_test.py"), "ro")

        def it_raises_before_any_container_when_a_host_path_is_missing(
            box: Botbox, tmp_path: Path, docker: dict[str, MagicMock], docker_build: MagicMock
        ) -> None:
            with pytest.raises(FileNotFoundError, match="gone"):
                box.run("true", mounts=[(tmp_path / "gone", "/gone", "ro")])
            docker_build.assert_not_called()
            docker["run"].assert_not_called()
            docker["cli"].assert_not_called()

    def describe_workdir() -> None:
        def it_starts_the_command_in_a_mounted_path(
            box: Botbox, daemon: Daemon, work: Path
        ) -> None:
            box.run("true", mounts=[(work, "/work", "rw")], workdir="/work")
            assert daemon.agent["workdir"] == "/work"

        def it_accepts_a_path_inside_a_mount(box: Botbox, daemon: Daemon, work: Path) -> None:
            box.run("true", mounts=[(work, "/work", "rw")], workdir=Path("/work/pkg"))
            assert daemon.agent["workdir"] == "/work/pkg"

        def it_accepts_the_agents_home(box: Botbox, daemon: Daemon) -> None:
            box.run("true", workdir="/home/node")
            assert daemon.agent["workdir"] == "/home/node"

        @pytest.mark.parametrize("workdir", ["/elsewhere", "/workspace", "/work/../etc", "/"])
        def it_raises_before_any_container_outside_every_mount(
            box: Botbox,
            work: Path,
            workdir: str,
            docker: dict[str, MagicMock],
            docker_build: MagicMock,
        ) -> None:
            with pytest.raises(ValueError, match="workdir"):
                box.run("true", mounts=[(work, "/work", "rw")], workdir=workdir)
            docker_build.assert_not_called()
            docker["run"].assert_not_called()
            docker["cli"].assert_not_called()

    def describe_logs() -> None:
        @pytest.mark.usefixtures("claude_writes_a_transcript")
        def it_returns_the_transcript_keyed_by_path_relative_to_the_home(box: Botbox) -> None:
            assert box.run("true").transcript == {
                ".claude/projects/-work/abc.jsonl": '{"type": "user"}\n'
            }

        @pytest.mark.usefixtures("claude_writes_a_transcript")
        def it_returns_the_proxy_log(box: Botbox) -> None:
            assert box.run("true").proxy == REFUSAL

        def it_has_tinyproxy_log_into_a_host_directory(box: Botbox, daemon: Daemon) -> None:
            box.run("true")
            assert volume(daemon.proxy, "/var/log/tinyproxy")[1] == "rw"
            assert daemon.proxy["files"]["/var/log/tinyproxy"] == {"tinyproxy.log": ""}

        def it_configures_tinyproxy_to_log_into_that_directory(
            box: Botbox, builds: list[dict[str, Any]]
        ) -> None:
            box.run("true")
            conf = (builds[1]["context"] / "tinyproxy.conf").read_text().splitlines()
            assert 'LogFile "/var/log/tinyproxy/tinyproxy.log"' in conf

        def it_lets_the_proxy_user_write_its_log(box: Botbox, daemon: Daemon) -> None:
            modes: list[int] = []
            daemon.container = lambda _home, proxy_log: modes.append(proxy_log.stat().st_mode)
            box.run("true")
            assert daemon.proxy["modes"]["/var/log/tinyproxy"] & 0o005 == 0o005
            assert modes[0] & 0o666 == 0o666

        def it_keeps_the_home_and_the_proxy_log_in_one_temporary_directory(
            box: Botbox, daemon: Daemon
        ) -> None:
            box.run("true")
            home = Path(volume(daemon.agent, "/home/node")[0])
            proxy_log = Path(volume(daemon.proxy, "/var/log/tinyproxy")[0])
            assert home.parent == proxy_log.parent

    def describe_teardown() -> None:
        def it_keeps_the_container_and_removes_the_sidecar_and_both_networks(
            box: Botbox, daemon: Daemon, docker: dict[str, MagicMock]
        ) -> None:
            result = box.run("true")
            assert result.container == "agent-container"
            docker["container"].remove.assert_called_once_with("proxy-container", force=True)
            [egress] = docker["network"].create.call_args.args
            assert [c.args[0] for c in docker["network"].remove.call_args_list] == [
                daemon.agent["networks"][0],
                egress,
            ]

        def it_tears_down_after_a_non_zero_exit(
            box: Botbox, daemon: Daemon, docker: dict[str, MagicMock]
        ) -> None:
            daemon.exit_code = 1
            box.run("false")
            docker["container"].remove.assert_called_once_with("proxy-container", force=True)
            assert docker["network"].remove.call_count == 2

        def it_tears_down_when_the_container_fails_to_start(
            box: Botbox, daemon: Daemon, docker: dict[str, MagicMock]
        ) -> None:
            record = docker["run"].side_effect

            def refuse_the_agent(image: str, command: Any = (), **options: Any) -> str:
                if not options.get("name"):
                    raise DockerException(["docker", "run"], 125, stderr=b"no such image")
                return str(record(image, command, **options))

            docker["run"].side_effect = refuse_the_agent
            with pytest.raises(DockerException):
                box.run("true")
            docker["container"].remove.assert_called_once_with("proxy-container", force=True)
            assert docker["network"].remove.call_count == 2
            scratch = Path(volume(daemon.proxy, "/var/log/tinyproxy")[0]).parent
            assert not scratch.exists()

        def it_tears_down_and_reraises_on_keyboard_interrupt(
            box: Botbox, daemon: Daemon, docker: dict[str, MagicMock]
        ) -> None:
            docker["logs"].side_effect = KeyboardInterrupt
            with pytest.raises(KeyboardInterrupt):
                box.run("sleep 600")
            removed = [c.args[0] for c in docker["container"].remove.call_args_list]
            assert removed == ["agent-container", "proxy-container"]
            assert docker["network"].remove.call_count == 2
            assert not Path(volume(daemon.agent, "/home/node")[0]).exists()

        def it_force_removes_the_running_container(
            box: Botbox, docker: dict[str, MagicMock]
        ) -> None:
            docker["logs"].side_effect = KeyboardInterrupt
            with pytest.raises(KeyboardInterrupt):
                box.run("sleep 600")
            assert docker["container"].remove.call_args_list[0].kwargs == {"force": True}

        def it_removes_both_networks_when_a_removal_fails(
            box: Botbox, docker: dict[str, MagicMock]
        ) -> None:
            docker["network"].remove.side_effect = [
                DockerException(["docker", "network", "rm"], 1),
                None,
            ]
            box.run("true")
            assert docker["network"].remove.call_count == 2

    def describe_when_the_daemon_dies_mid_run() -> None:
        @pytest.fixture
        def dead(daemon: Daemon, docker: dict[str, MagicMock]) -> None:
            daemon.dies_mid_run = True
            daemon.logs = [("stdout", b"halfway\n"), ("stderr", b"warn\n")]
            gone = DockerException(["docker"], 1, stderr=b"Cannot connect to the Docker daemon")
            docker["container"].remove.side_effect = gone
            docker["network"].remove.side_effect = gone
            docker["network"].disconnect.side_effect = gone

        @pytest.mark.usefixtures("dead", "claude_writes_a_transcript")
        def it_still_returns_a_result(box: Botbox) -> None:
            assert isinstance(box.run("true"), RunResult)

        @pytest.mark.usefixtures("dead")
        def it_keeps_the_output_that_arrived(box: Botbox) -> None:
            result = box.run("true")
            assert (result.stdout, result.stderr) == ("halfway\n", "warn\n")

        @pytest.mark.usefixtures("dead")
        def it_reports_no_exit_code_as_minus_one(box: Botbox) -> None:
            assert box.run("true").exit_code == -1

        @pytest.mark.usefixtures("dead", "claude_writes_a_transcript")
        def it_keeps_the_transcript_written_before_it_died(box: Botbox) -> None:
            assert box.run("true").transcript == {
                ".claude/projects/-work/abc.jsonl": '{"type": "user"}\n'
            }

        @pytest.mark.usefixtures("dead", "claude_writes_a_transcript")
        def it_keeps_the_proxy_log_written_before_it_died(box: Botbox) -> None:
            assert box.run("true").proxy == REFUSAL

        @pytest.mark.usefixtures("dead")
        def it_still_deletes_the_temporary_directory(box: Botbox, daemon: Daemon) -> None:
            box.run("true")
            assert not Path(volume(daemon.agent, "/home/node")[0]).parent.exists()

        @pytest.mark.usefixtures("dead")
        def it_still_tries_to_remove_the_sidecar_and_both_networks(
            box: Botbox, docker: dict[str, MagicMock]
        ) -> None:
            box.run("true")
            docker["container"].remove.assert_called_once_with("proxy-container", force=True)
            assert docker["network"].remove.call_count == 2

        def it_keeps_the_exit_code_when_only_teardown_fails(
            box: Botbox, daemon: Daemon, docker: dict[str, MagicMock]
        ) -> None:
            daemon.exit_code = 4
            docker["container"].remove.side_effect = DockerException(["docker"], 1)
            assert box.run("true").exit_code == 4
