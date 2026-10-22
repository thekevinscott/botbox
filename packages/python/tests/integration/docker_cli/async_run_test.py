"""`AsyncBotbox.run()` against a fake `docker` on PATH that keeps each container's state."""

import asyncio
from pathlib import Path

import pytest
from fake_docker_test import REFUSAL, Daemon, homes, option, token

from botbox import AsyncBotbox, DockerException, RunResult


def describe_async_run() -> None:
    def describe_the_result() -> None:
        async def it_returns_what_the_run_left(box: AsyncBotbox, daemon: Daemon) -> None:
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
            box: AsyncBotbox, daemon: Daemon
        ) -> None:
            daemon.set(proxy_log="GET http://caf\xe9/ HTTP/1.1\n")
            assert (await box.run("true")).proxy == "GET http://caf\ufffd/ HTTP/1.1\n"

        async def it_returns_the_result_and_warns_when_the_proxy_log_will_not_read(
            box: AsyncBotbox, daemon: Daemon
        ) -> None:
            daemon.agent("true", stdout="out\n")
            daemon.set(proxy_log_unreadable=True)
            with pytest.warns(RuntimeWarning, match="^botbox could not read its proxy log: "):
                result = await box.run("true")
            assert (result.stdout, result.exit_code, result.proxy) == ("out\n", 0, "")

        async def it_reads_the_exit_code_from_the_stopped_container(
            box: AsyncBotbox, daemon: Daemon
        ) -> None:
            daemon.agent("exit 125", exit=125)
            assert (await box.run("exit 125")).exit_code == 125
            name = f"botbox-agent-{token(daemon)}"
            assert ["container", "inspect", "--format", "json", name] in daemon.calls

        async def it_returns_minus_one_with_warnings_when_the_daemon_goes_away(
            box: AsyncBotbox, daemon: Daemon
        ) -> None:
            daemon.agent("true", stdout="partial\n", mode="daemon_gone")
            with pytest.warns(RuntimeWarning) as warned:
                result = await box.run("true")
            assert [str(w.message).split(":")[0] for w in warned] == [
                f"botbox could not remove its agent container botbox-agent-{token(daemon)}",
                f"botbox could not remove its proxy botbox-proxy-{token(daemon)}",
            ]
            assert result.exit_code == -1
            assert result.stdout == "partial\n"
            assert result.transcript == {".claude/projects/-work/abc.jsonl": '{"type": "user"}\n'}

    def describe_the_containers() -> None:
        async def it_names_and_labels_both_with_one_run_token(
            box: AsyncBotbox, daemon: Daemon
        ) -> None:
            await box.run("true")
            [proxy] = daemon.runs("botbox-proxy-")
            [agent] = daemon.runs("botbox-agent-")
            run = token(daemon)
            assert len(run) == 12
            assert option(proxy, "--name") == f"botbox-proxy-{run}"
            assert option(proxy, "--label") == option(agent, "--label") == f"botbox.run={run}"

        async def it_starts_neither_with_remove_on_exit(box: AsyncBotbox, daemon: Daemon) -> None:
            await box.run("true")
            assert all("--rm" not in run for run in daemon.runs("botbox-"))

        async def it_runs_the_agent_in_the_proxys_pid_namespace(
            box: AsyncBotbox, daemon: Daemon
        ) -> None:
            await box.run("true")
            [agent] = daemon.runs("botbox-agent-")
            assert option(agent, "--pid") == f"container:botbox-proxy-{token(daemon)}"
            assert option(agent, "--network") == "none"
            assert agent[-3:] == ["sh", "-c", "true"]

        async def it_removes_both_once_the_run_is_done(box: AsyncBotbox, daemon: Daemon) -> None:
            await box.run("true")
            run = token(daemon)
            assert daemon.removed == [f"botbox-agent-{run}", f"botbox-proxy-{run}"]
            assert daemon.containers == []

        async def it_removes_the_temp_home(box: AsyncBotbox, daemon: Daemon, temp: Path) -> None:
            await box.run("true")
            assert homes(temp) == []
            [agent] = daemon.runs("botbox-agent-")
            home = next(v for v in agent if v.endswith(":/home/user:rw")).split(":")[0]
            assert Path(home).parent.name.startswith(f"botbox-{token(daemon)}-")

    def describe_failure() -> None:
        async def it_raises_when_the_client_dies_while_the_daemon_is_up(
            box: AsyncBotbox, daemon: Daemon
        ) -> None:
            daemon.agent("true", stderr="lost\n", mode="client_dies")
            with pytest.raises(DockerException) as raised:
                await box.run("true")
            assert raised.value.return_code == -9
            assert raised.value.stderr == "lost\n"
            assert daemon.containers == []

        async def it_raises_when_the_client_is_killed_after_the_container_exits(
            box: AsyncBotbox, daemon: Daemon
        ) -> None:
            daemon.agent("true", stdout="trunc", mode="client_dies_after_exit")
            with pytest.raises(DockerException) as raised:
                await box.run("true")
            assert raised.value.return_code == -9
            assert daemon.containers == []

        async def it_raises_when_the_container_never_ran(box: AsyncBotbox, daemon: Daemon) -> None:
            daemon.agent("true", missing=True)
            with pytest.raises(DockerException) as raised:
                await box.run("true")
            assert raised.value.return_code == 125
            assert "Unable to find image" in raised.value.stderr
            assert daemon.containers == []

        async def it_raises_with_the_proxys_output_when_it_will_not_start(
            box: AsyncBotbox, daemon: Daemon, temp: Path
        ) -> None:
            daemon.set(proxy_fails=True)
            with pytest.raises(RuntimeError, match="did not start:\ntinyproxy: bad config"):
                await box.run("true")
            assert daemon.runs("botbox-agent-") == []
            assert homes(temp) == []

        async def it_keeps_the_error_and_warns_when_the_proxy_log_will_not_read(
            box: AsyncBotbox, daemon: Daemon
        ) -> None:
            daemon.agent("true", missing=True)
            daemon.set(proxy_log_unreadable=True)
            with (
                pytest.warns(RuntimeWarning, match="could not read its proxy log"),
                pytest.raises(DockerException) as raised,
            ):
                await box.run("true")
            assert raised.value.return_code == 125

        async def it_returns_the_result_and_warns_when_teardown_fails(
            box: AsyncBotbox, daemon: Daemon
        ) -> None:
            daemon.set(rm_fails=True)
            with pytest.warns(RuntimeWarning) as warned:
                result = await box.run("true")
            assert result.exit_code == 0
            assert [str(w.message).split(":")[0] for w in warned] == [
                f"botbox could not remove its agent container botbox-agent-{token(daemon)}",
                f"botbox could not remove its proxy botbox-proxy-{token(daemon)}",
            ]

    def describe_cancelling() -> None:
        async def it_tears_down_the_run_when_cancelled(
            box: AsyncBotbox, daemon: Daemon, temp: Path
        ) -> None:
            daemon.agent("sleep 600", mode="hang")
            run = asyncio.ensure_future(box.run("sleep 600"))
            await daemon.hanging()
            run.cancel()
            await asyncio.wait({run}, timeout=10)
            assert run.cancelled()
            assert daemon.containers == []
            assert homes(temp) == []

        async def it_finishes_tearing_down_through_a_second_cancel(
            box: AsyncBotbox, daemon: Daemon, temp: Path
        ) -> None:
            daemon.agent("sleep 600", mode="hang")
            daemon.set(rm_seconds=0.3)
            run = asyncio.ensure_future(box.run("sleep 600"))
            await daemon.hanging()
            run.cancel()
            await asyncio.sleep(0.1)
            run.cancel()
            await asyncio.wait({run}, timeout=10)
            assert run.cancelled()
            assert daemon.containers == []
            assert homes(temp) == []

        async def it_tears_down_the_run_when_a_timeout_fires(
            box: AsyncBotbox, daemon: Daemon, temp: Path
        ) -> None:
            daemon.agent("sleep 600", mode="hang")
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(1):
                    await box.run("sleep 600")
            assert daemon.containers == []
            assert homes(temp) == []

        async def it_raises_a_sibling_runs_error_unwrapped_in_a_task_group(
            box: AsyncBotbox, daemon: Daemon, temp: Path
        ) -> None:
            daemon.agent("sleep 600", mode="hang")
            daemon.agent("false", missing=True)

            async def fail_once_hanging() -> RunResult:
                await daemon.hanging()
                return await box.run("false")

            with pytest.raises(ExceptionGroup) as raised:
                async with asyncio.TaskGroup() as group:
                    group.create_task(box.run("sleep 600"))
                    group.create_task(fail_once_hanging())
            [error] = raised.value.exceptions
            assert isinstance(error, DockerException)
            assert daemon.containers == []
            assert homes(temp) == []
