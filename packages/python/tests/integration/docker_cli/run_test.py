"""`Botbox.run()` against a fake `docker` on PATH that keeps each container's state."""

import asyncio
import contextlib
import os
from pathlib import Path
from typing import Any

import pytest
from fake_docker_test import REFUSAL, Daemon, homes, option, runs, token, volume

from botbox import (
    Botbox,
    ClaudeAgent,
    CodexAgent,
    DockerException,
    PiAgent,
    RunResult,
    Timeout,
)

RELAY_COPY = "COPY --from=botbox --chmod=755 botbox-relay /usr/local/bin/botbox-relay"


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


def agent_run(daemon: Daemon) -> list[str]:
    [run] = daemon.runs("botbox-agent-")
    return run


def started_nothing(daemon: Daemon) -> bool:
    return [c for c in daemon.calls if c[0] != "buildx"] == []


def describe_run() -> None:
    def describe_the_result() -> None:
        async def it_returns_what_the_run_left(box: Botbox, daemon: Daemon) -> None:
            daemon.agent("claude -p hi", stdout="out\n", stderr="err\n", exit=3)
            daemon.set(proxy_log=REFUSAL)
            result = await box.run("claude -p hi")
            assert result == RunResult(
                stdout="out\n",
                stderr="err\n",
                exit_code=3,
                transcript={".claude/projects/-work/abc.jsonl": '{"type": "user"}\n'},
                proxy=REFUSAL,
                image="botbox-claude:latest",
            )

        async def it_replaces_proxy_log_bytes_that_are_not_utf8(
            box: Botbox, daemon: Daemon, output: Path
        ) -> None:
            daemon.set(proxy_log="GET http://caf\xe9/ HTTP/1.1\n")
            assert (
                await box.run("true", output=output)
            ).proxy == "GET http://caf\ufffd/ HTTP/1.1\n"

        async def it_returns_the_result_and_warns_when_the_proxy_log_will_not_read(
            box: Botbox, daemon: Daemon, output: Path
        ) -> None:
            daemon.agent("true", stdout="out\n")
            daemon.set(proxy_log_unreadable=True)
            with pytest.warns(RuntimeWarning, match="^botbox could not read its proxy log: "):
                result = await box.run("true", output=output)
            assert (result.stdout, result.exit_code, result.proxy) == ("", 0, "")
            assert (output / "stdout.txt").read_text() == "out\n"

        async def it_reads_the_exit_code_from_the_stopped_container(
            box: Botbox, daemon: Daemon, output: Path
        ) -> None:
            daemon.agent("exit 125", exit=125)
            assert (await box.run("exit 125", output=output)).exit_code == 125
            name = f"botbox-agent-{token(daemon)}"
            assert ["container", "inspect", "--format", "json", name] in daemon.calls

        async def it_returns_minus_one_with_warnings_when_the_daemon_goes_away(
            box: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            daemon.agent("true", stdout="partial\n", mode="daemon_gone")
            daemon.set(proxy_log=REFUSAL)
            with pytest.warns(RuntimeWarning) as warned:
                result = await box.run("true", output=output)
            assert [str(w.message).split(":")[0] for w in warned] == [
                f"botbox could not remove its agent container botbox-agent-{token(daemon)}",
                f"botbox could not remove its proxy botbox-proxy-{token(daemon)}",
            ]
            assert result.exit_code == -1
            assert result.stdout == ""
            assert (output / "stdout.txt").read_text() == "partial\n"
            assert result.transcript == {".claude/projects/-work/abc.jsonl": '{"type": "user"}\n'}
            assert result.proxy == REFUSAL
            assert homes(temp) == []

    def describe_the_containers() -> None:
        async def it_names_and_labels_both_with_one_run_token(box: Botbox, daemon: Daemon) -> None:
            await box.run("true")
            [proxy] = daemon.runs("botbox-proxy-")
            [agent] = daemon.runs("botbox-agent-")
            run = token(daemon)
            assert len(run) == 12
            assert option(proxy, "--name") == f"botbox-proxy-{run}"
            assert option(proxy, "--label") == option(agent, "--label") == f"botbox.run={run}"

        async def it_starts_neither_with_remove_on_exit(box: Botbox, daemon: Daemon) -> None:
            await box.run("true")
            assert all("--rm" not in run for run in daemon.runs("botbox-"))

        async def it_runs_the_agent_in_the_proxys_pid_namespace(
            box: Botbox, daemon: Daemon
        ) -> None:
            await box.run("true")
            [agent] = daemon.runs("botbox-agent-")
            assert option(agent, "--pid") == f"container:botbox-proxy-{token(daemon)}"
            assert option(agent, "--network") == "none"
            assert agent[-3:] == ["sh", "-c", "true"]

        async def it_removes_both_once_the_run_is_done(box: Botbox, daemon: Daemon) -> None:
            await box.run("true")
            run = token(daemon)
            assert daemon.removed == [f"botbox-agent-{run}", f"botbox-proxy-{run}"]
            assert daemon.containers == []

        async def it_removes_the_temp_home(box: Botbox, daemon: Daemon, temp: Path) -> None:
            await box.run("true")
            assert homes(temp) == []
            [agent] = daemon.runs("botbox-agent-")
            home = next(v for v in agent if v.endswith(":/home/user:rw")).split(":")[0]
            assert Path(home).parent == runs(temp) / token(daemon)

        async def it_uses_a_new_temp_home_and_socket_directory_each_run(
            box: Botbox, daemon: Daemon
        ) -> None:
            await box.run("true")
            await box.run("true")
            first, second = daemon.runs("botbox-agent-")
            assert volume(first, "/home/user") != volume(second, "/home/user")
            assert volume(first, "/run/botbox") != volume(second, "/run/botbox")

        async def it_removes_nothing_more_when_the_block_exits(box: Botbox, daemon: Daemon) -> None:
            async with box:
                await box.run("true")
                removed = daemon.removed
            assert daemon.removed == removed
            assert len(removed) == 2

    def describe_the_build() -> None:
        async def it_starts_nothing_when_the_agent_image_fails(
            box: Botbox, daemon: Daemon, temp: Path
        ) -> None:
            daemon.set(builds_fail=["botbox-claude:latest"])
            with pytest.raises(DockerException):
                await box.run("true")
            assert started_nothing(daemon)
            assert homes(temp) == []

        @pytest.mark.parametrize("agent_class", [ClaudeAgent, CodexAgent, PiAgent])
        def it_ships_the_relay_into_every_agent_image(
            agent_class: type[ClaudeAgent | CodexAgent | PiAgent],
        ) -> None:
            text = agent_class.dockerfile.read_text()
            assert RELAY_COPY in text
            assert "socat" in text

    def describe_an_api_key() -> None:
        @pytest.mark.parametrize(
            ("agent", "key"),
            [
                (lambda home: ClaudeAgent(api_key="sk-test", host_home=home), "sk-test"),
                (lambda home: CodexAgent(api_key="sk-test", host_home=home), "sk-test"),
                (
                    lambda home: PiAgent("openrouter", api_key="sk-or-test", host_home=home),
                    "sk-or-test",
                ),
            ],
            ids=["claude", "codex", "pi"],
        )
        async def it_keeps_the_key_out_of_every_docker_command_and_deletes_it_afterwards(
            daemon: Daemon, temp: Path, tmp_path: Path, agent: Any, key: str
        ) -> None:
            await Botbox(agent(tmp_path / "missing")).run("true")
            assert key not in repr(daemon.calls)
            assert homes(temp) == []

    def describe_mounts() -> None:
        async def it_bind_mounts_each_host_path_with_its_mode(
            box: Botbox, daemon: Daemon, tests: Path, work: Path
        ) -> None:
            await box.run("true", mounts=[(tests, "/tests", "ro"), (work, "/work", "rw")])
            run = agent_run(daemon)
            assert volume(run, "/tests") == (str(tests), "ro")
            assert volume(run, "/work") == (str(work), "rw")

        async def it_resolves_relative_host_paths_against_the_working_directory(
            box: Botbox, daemon: Daemon, tests: Path, tmp_path: Path
        ) -> None:
            with contextlib.chdir(tmp_path):
                await box.run("true", mounts=[("./tests", "/tests", "ro")])
            assert volume(agent_run(daemon), "/tests") == (str(tests), "ro")

        async def it_accepts_paths_as_strings_or_paths(
            box: Botbox, daemon: Daemon, work: Path
        ) -> None:
            await box.run("true", mounts=[(str(work), Path("/work"), "rw")])
            assert volume(agent_run(daemon), "/work") == (str(work), "rw")

        async def it_mounts_a_single_file(box: Botbox, daemon: Daemon, tests: Path) -> None:
            await box.run("true", mounts=[(tests / "a_test.py", "/a_test.py", "ro")])
            assert volume(agent_run(daemon), "/a_test.py") == (str(tests / "a_test.py"), "ro")

        async def it_creates_a_missing_host_path_as_a_directory_and_mounts_it(
            box: Botbox, daemon: Daemon, tmp_path: Path
        ) -> None:
            await box.run("true", mounts=[(tmp_path / "new", "/new", "rw")])
            assert (tmp_path / "new").is_dir()
            assert volume(agent_run(daemon), "/new") == (str(tmp_path / "new"), "rw")

    def describe_workdir() -> None:
        async def it_accepts_the_agents_home(box: Botbox, daemon: Daemon) -> None:
            await box.run("true", workdir="/home/user")
            assert option(agent_run(daemon), "--workdir") == "/home/user"

        @pytest.mark.parametrize("workdir", ["/elsewhere", "/workspace", "/work/../etc", "/"])
        async def it_raises_before_anything_outside_every_mount(
            box: Botbox, daemon: Daemon, work: Path, workdir: str
        ) -> None:
            with pytest.raises(ValueError, match="workdir"):
                await box.run("true", mounts=[(work, "/work", "rw")], workdir=workdir)
            assert daemon.calls == []

    def describe_failure() -> None:
        async def it_raises_when_the_client_dies_while_the_daemon_is_up(
            box: Botbox, daemon: Daemon, output: Path
        ) -> None:
            daemon.agent("true", stderr="lost\n", mode="client_dies")
            with pytest.raises(DockerException) as raised:
                await box.run("true", output=output)
            assert raised.value.return_code == -9
            assert raised.value.stderr == f"See {output / 'stderr.txt'}"
            assert (output / "stderr.txt").read_text() == "lost\n"
            assert daemon.containers == []

        async def it_raises_when_the_client_is_killed_after_the_container_exits(
            box: Botbox, daemon: Daemon, output: Path
        ) -> None:
            daemon.agent("true", stdout="trunc", mode="client_dies_after_exit")
            with pytest.raises(DockerException) as raised:
                await box.run("true", output=output)
            assert raised.value.return_code == -9
            assert daemon.containers == []

        async def it_raises_when_the_container_never_ran(
            box: Botbox, daemon: Daemon, output: Path
        ) -> None:
            daemon.agent("true", missing=True)
            with pytest.raises(DockerException) as raised:
                await box.run("true", output=output)
            assert raised.value.return_code == 125
            assert "Unable to find image" in (output / "stderr.txt").read_text()
            assert daemon.containers == []

        async def it_raises_with_the_proxys_output_when_it_will_not_start(
            box: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            daemon.set(proxy_fails=True)
            with pytest.raises(RuntimeError, match="did not start:\ntinyproxy: bad config"):
                await box.run("true", output=output)
            assert daemon.runs("botbox-agent-") == []
            assert homes(temp) == []

        async def it_keeps_the_error_and_warns_when_the_proxy_log_will_not_read(
            box: Botbox, daemon: Daemon, output: Path
        ) -> None:
            daemon.agent("true", missing=True)
            daemon.set(proxy_log_unreadable=True)
            with (
                pytest.warns(RuntimeWarning, match="could not read its proxy log"),
                pytest.raises(DockerException) as raised,
            ):
                await box.run("true", output=output)
            assert raised.value.return_code == 125

        async def it_returns_the_result_and_warns_when_teardown_fails(
            box: Botbox, daemon: Daemon, output: Path
        ) -> None:
            daemon.set(rm_fails=True)
            with pytest.warns(RuntimeWarning) as warned:
                result = await box.run("true", output=output)
            assert result.exit_code == 0
            assert [str(w.message).split(":")[0] for w in warned] == [
                f"botbox could not remove its agent container botbox-agent-{token(daemon)}",
                f"botbox could not remove its proxy botbox-proxy-{token(daemon)}",
            ]

    def describe_cancelling() -> None:
        async def it_tears_down_the_run_when_cancelled(
            box: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            daemon.agent("sleep 600", mode="hang", stdout="partial\n", stderr="err\n")
            run = asyncio.ensure_future(box.run("sleep 600", output=output))
            await daemon.hanging()
            run.cancel()
            await asyncio.wait({run}, timeout=10)
            assert run.cancelled()
            assert daemon.containers == []
            assert homes(temp) == []
            assert (output / "stdout.txt").read_text() == "partial\n"
            assert (output / "stderr.txt").read_text() == "err\n"

        async def it_finishes_tearing_down_through_a_second_cancel(
            box: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            daemon.agent("sleep 600", mode="hang", stdout="partial\n", stderr="err\n")
            daemon.set(rm_seconds=0.3)
            run = asyncio.ensure_future(box.run("sleep 600", output=output))
            await daemon.hanging()
            run.cancel()
            await asyncio.sleep(0.1)
            run.cancel()
            await asyncio.wait({run}, timeout=10)
            assert run.cancelled()
            assert daemon.containers == []
            assert homes(temp) == []
            assert (output / "stdout.txt").read_text() == "partial\n"
            assert (output / "stderr.txt").read_text() == "err\n"

        async def it_tears_down_the_run_when_a_timeout_fires(
            box: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            daemon.agent("sleep 600", mode="hang", stdout="partial\n", stderr="err\n")
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(1):
                    await box.run("sleep 600", output=output)
            assert daemon.containers == []
            assert homes(temp) == []
            assert (output / "stdout.txt").read_text() == "partial\n"
            assert (output / "stderr.txt").read_text() == "err\n"

        async def it_tears_down_and_raises_what_the_run_left_when_its_timeout_runs_out(
            box: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            daemon.agent("sleep 600", mode="hang", stdout="partial\n")
            daemon.set(proxy_log=REFUSAL)
            with pytest.raises(Timeout) as raised:
                await Botbox(box.agent, timeout=2).run("sleep 600", output=output)
            assert (output / "stdout.txt").read_text() == "partial\n"
            assert raised.value.result == RunResult(
                stdout="",
                stderr="",
                exit_code=-1,
                transcript={".claude/projects/-work/abc.jsonl": '{"type": "user"}\n'},
                proxy=REFUSAL,
                image="botbox-claude:latest",
            )
            assert daemon.containers == []
            assert homes(temp) == []

        async def it_raises_a_sibling_runs_error_unwrapped_in_a_task_group(
            box: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            daemon.agent("sleep 600", mode="hang", stdout="partial\n", stderr="err\n")
            daemon.agent("false", missing=True)

            async def fail_once_hanging() -> RunResult:
                await daemon.hanging()
                return await box.run("false", output=output / "failed")

            with pytest.raises(ExceptionGroup) as raised:
                async with asyncio.TaskGroup() as group:
                    group.create_task(box.run("sleep 600", output=output / "sleeping"))
                    group.create_task(fail_once_hanging())
            [error] = raised.value.exceptions
            assert isinstance(error, DockerException)
            assert daemon.containers == []
            assert homes(temp) == []


def describe_the_agent_user() -> None:
    async def it_is_the_host_user_with_the_staged_home(box: Botbox, daemon: Daemon) -> None:
        await Botbox(box.agent).run("true")
        [agent] = daemon.runs("botbox-agent-")
        assert option(agent, "--user") == f"{os.getuid()}:{os.getgid()}"
        assert "HOME=/home/user" in agent


def describe_run_output() -> None:
    async def it_preserves_large_streams_in_files(
        box: Botbox, daemon: Daemon, tmp_path: Path
    ) -> None:
        stdout, stderr = "x" * 200_000, "y" * 200_000
        daemon.agent("true", stdout=stdout, stderr=stderr, exit=7)
        result = await box.run("true", output=tmp_path)
        assert (result.stdout, result.stderr, result.exit_code) == ("", "", 7)
        assert (tmp_path / "stdout.txt").read_text() == stdout
        assert (tmp_path / "stderr.txt").read_text() == stderr
        assert daemon.containers == []

    async def it_points_to_stderr_when_the_container_never_ran(
        box: Botbox, daemon: Daemon, tmp_path: Path
    ) -> None:
        daemon.agent("true", missing=True)
        with pytest.raises(DockerException) as raised:
            await box.run("true", output=tmp_path)
        assert raised.value.stderr == f"See {tmp_path / 'stderr.txt'}"
        assert "Unable to find image" in (tmp_path / "stderr.txt").read_text()
        assert daemon.containers == []

    async def it_keeps_live_files_after_cancellation(
        box: Botbox, daemon: Daemon, tmp_path: Path
    ) -> None:
        daemon.agent("sleep 600", stdout="partial\n", stderr="error\n", mode="hang")
        task = asyncio.create_task(box.run("sleep 600", output=tmp_path))
        await daemon.hanging()
        assert (tmp_path / "stdout.txt").read_text() == "partial\n"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (tmp_path / "stderr.txt").read_text() == "error\n"
        assert daemon.containers == []

    async def it_keeps_files_and_empty_stream_fields_after_timeout(
        box: Botbox, daemon: Daemon, tmp_path: Path
    ) -> None:
        daemon.agent("sleep 600", stdout="partial\n", mode="hang")
        with pytest.raises(Timeout) as raised:
            await box.run("sleep 600", output=tmp_path, timeout=2)
        result = raised.value.result
        assert (result.stdout, result.stderr, result.exit_code) == ("", "", -1)
        assert (tmp_path / "stdout.txt").read_text() == "partial\n"
        assert daemon.containers == []


@pytest.fixture
def output(tmp_path: Path) -> Path:
    return tmp_path / "output"


def describe_output_reuse() -> None:
    async def it_replaces_both_streams_on_success_and_early_failure(
        box: Botbox, daemon: Daemon, output: Path
    ) -> None:
        daemon.agent("first", stdout="old stdout", stderr="old stderr")
        await box.run("first", output=output)
        (output / "keep").write_text("keep")
        daemon.agent("second", stdout="new", exit=3)
        assert (await box.run("second", output=output)).exit_code == 3
        assert (output / "stdout.txt").read_text() == "new"
        assert (output / "stderr.txt").read_text() == ""
        daemon.set(proxy_fails=True)
        with pytest.raises(RuntimeError, match="did not start"):
            await box.run("third", output=output)
        assert (output / "stdout.txt").read_text() == ""
        assert (output / "stderr.txt").read_text() == ""
        assert (output / "keep").read_text() == "keep"
        assert daemon.containers == []
