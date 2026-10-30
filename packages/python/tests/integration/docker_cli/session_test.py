"""`Botbox.session()` against a fake `docker` on PATH that keeps each container's state."""

import asyncio
import os
from pathlib import Path

import pytest
from fake_docker_test import LISTENING, REFUSAL, Daemon, option, temp_dirs, token

from botbox import (
    Botbox,
    ClaudeAgent,
    CodexAgent,
    DockerException,
    RunResult,
    Timeout,
)

SESSION = ClaudeAgent().session_command()


@pytest.fixture
def output(tmp_path: Path) -> Path:
    return tmp_path / "output"


def assert_left(output: Path, said: str) -> None:
    """The session's stdout and transcript are in `output`."""
    assert f'"said": "{said}"' in (output / "stdout.txt").read_text()
    assert (output / "transcripts" / "-work" / "abc.jsonl").is_file()


@pytest.fixture
def talker(box: Botbox, daemon: Daemon) -> Botbox:
    """The box, its agent's session planned to answer each message."""
    daemon.agent(SESSION, mode="session", stdout="booting\n")
    return box


def stdout(output: Path) -> str:
    return (output / "stdout.txt").read_text()


def describe_session() -> None:
    def describe_a_turn() -> None:
        async def it_streams_the_events_up_to_the_turns_end(talker: Botbox, output: Path) -> None:
            async with talker.session(output=output) as live:
                events = [event async for event in live.stream("hi")]
            assert events == [
                {"type": "assistant", "said": "hi"},
                {"type": "result", "result": "HI"},
            ]

        async def it_collects_a_turn_and_keeps_the_conversation_going(
            talker: Botbox, output: Path
        ) -> None:
            async with talker.session(output=output) as live:
                first = await live.message("one")
                second = await live.message("two")
            assert [turn[-1]["result"] for turn in (first, second)] == ["ONE", "TWO"]

        async def it_skips_the_rest_of_a_turn_left_early(talker: Botbox, output: Path) -> None:
            async with talker.session(output=output) as live:
                async for _ in live.stream("one"):
                    break
                assert (await live.message("two"))[-1] == {"type": "result", "result": "TWO"}

        async def it_reads_events_past_a_large_line_that_is_not_one(
            box: Botbox, daemon: Daemon, output: Path
        ) -> None:
            large = "x" * (1 << 20) + "\n"
            daemon.agent(SESSION, mode="session", stdout=large)
            async with box.session(output=output) as live:
                assert (await live.message("hi"))[-1] == {"type": "result", "result": "HI"}
            assert stdout(output).startswith(large)

        async def it_ends_a_turn_the_cli_cuts_short_with_what_arrived(
            talker: Botbox, output: Path
        ) -> None:
            with pytest.raises(DockerException) as raised:
                async with talker.session(output=output) as live:
                    events = await live.message("die")
            assert events == [{"type": "assistant", "said": "die"}]
            assert raised.value.return_code == -9

    def describe_the_result() -> None:
        async def it_leaves_only_the_exit_code_once_the_block_ends(talker: Botbox) -> None:
            async with talker.session() as live:
                await live.message("hi")
                assert talker.result is None
            assert talker.result == RunResult(0, oom_killed=False)

        async def it_keeps_the_open_sessions_result_when_a_second_is_refused(
            talker: Botbox,
        ) -> None:
            async with talker.session() as live:
                with pytest.raises(RuntimeError, match="already has an open session"):
                    async with talker.session():
                        pass
                await live.message("hi")
            assert talker.result == RunResult(0, oom_killed=False)

        async def it_reads_the_exit_code_from_the_stopped_container(
            box: Botbox, daemon: Daemon, output: Path
        ) -> None:
            daemon.agent(SESSION, mode="session", exit=3)
            async with box.session(output=output):
                pass
            assert box.result is not None
            assert box.result.exit_code == 3

        async def it_returns_the_result_and_warns_when_teardown_fails(
            talker: Botbox, daemon: Daemon, output: Path
        ) -> None:
            daemon.set(rm_fails=True)
            with pytest.warns(RuntimeWarning) as warned:
                async with talker.session(output=output) as live:
                    await live.message("hi")
            assert talker.result is not None
            assert talker.result.exit_code == 0
            assert [str(w.message).split(":")[0] for w in warned] == [
                f"botbox could not remove its agent container botbox-agent-{token(daemon)}",
                f"botbox could not remove its proxy botbox-proxy-{token(daemon)}",
            ]

    def describe_output() -> None:
        async def it_reads_events_from_its_own_copy_when_the_output_is_truncated(
            talker: Botbox, output: Path
        ) -> None:
            async with talker.session(output=output) as live:
                first = await live.message("one")
                (output / "stdout.txt").write_bytes(b"")
                second = await live.message("two")
            assert first[-1] == {"type": "result", "result": "ONE"}
            assert second[-1] == {"type": "result", "result": "TWO"}
            assert talker.result == RunResult(0, oom_killed=False)

        async def it_drops_an_output_file_that_fails_and_carries_on(
            talker: Botbox, output: Path
        ) -> None:
            output.mkdir()
            (output / "stdout.txt").symlink_to("/dev/full")
            with pytest.warns(RuntimeWarning, match="stopped writing to .*stdout.txt"):
                async with talker.session(output=output) as live:
                    events = await live.message("one")
            assert events[-1] == {"type": "result", "result": "ONE"}
            assert talker.result == RunResult(0, oom_killed=False)
            assert (output / "stderr.txt").is_file()

        async def it_leaves_nothing_behind_without_output(talker: Botbox, temp: Path) -> None:
            async with talker.session() as live:
                assert (await live.message("one"))[-1] == {"type": "result", "result": "ONE"}
            assert talker.result == RunResult(0, oom_killed=False)
            assert list(temp.iterdir()) == []

        async def it_streams_events_from_the_files_it_writes(
            talker: Botbox, daemon: Daemon, temp: Path, tmp_path: Path
        ) -> None:
            daemon.agent(SESSION, mode="session", stdout="booting\n", stderr="diagnostic\n")
            daemon.set(proxy_log=REFUSAL)
            output = tmp_path / "output"
            async with talker.session(output=output) as live:
                first = await live.message("one")
                second = await live.message("two")
            assert first[-1] == {"type": "result", "result": "ONE"}
            assert second[-1] == {"type": "result", "result": "TWO"}
            assert talker.result == RunResult(0, oom_killed=False)
            stdout = (output / "stdout.txt").read_text()
            assert stdout.startswith("booting\n")
            assert '{"type": "result", "result": "TWO"}\n' in stdout
            assert (output / "stderr.txt").read_text() == "diagnostic\n"
            transcript = output / "transcripts" / "-work" / "abc.jsonl"
            assert transcript.read_text() == '{"type": "user"}\n'
            assert (output / "proxy.log").read_text() == LISTENING + REFUSAL
            assert daemon.containers == []
            assert temp_dirs(temp) == []

        async def it_raises_with_stderr_when_the_container_never_ran(
            box: Botbox, daemon: Daemon, tmp_path: Path
        ) -> None:
            daemon.agent(SESSION, missing=True)
            with pytest.raises(DockerException) as raised:
                async with box.session(output=tmp_path) as live:
                    assert await live.message("hi") == []
            assert "Unable to find image" in raised.value.stderr
            assert (tmp_path / "stderr.txt").read_text() == raised.value.stderr

        async def it_ends_a_turn_the_cli_cuts_short_and_leaves_the_files(
            talker: Botbox, daemon: Daemon, temp: Path, tmp_path: Path
        ) -> None:
            with pytest.raises(DockerException) as raised:
                async with talker.session(output=tmp_path) as live:
                    events = await live.message("die")
            assert events == [{"type": "assistant", "said": "die"}]
            assert raised.value.return_code == -9
            assert raised.value.stderr == ""
            assert talker.result == RunResult(-1)
            assert '"said": "die"' in (tmp_path / "stdout.txt").read_text()
            assert daemon.containers == []
            assert temp_dirs(temp) == []

        async def it_tears_down_when_cancelled_mid_turn(
            talker: Botbox, daemon: Daemon, temp: Path, tmp_path: Path
        ) -> None:

            async def talk() -> None:
                async with talker.session(output=tmp_path) as live:
                    await live.message("hang")

            task = asyncio.ensure_future(talk())
            await daemon.hanging()
            task.cancel()
            await asyncio.wait({task}, timeout=10)
            assert task.cancelled()
            assert talker.result == RunResult(-1)
            assert '"said": "hang"' in (tmp_path / "stdout.txt").read_text()
            transcript = tmp_path / "transcripts" / "-work" / "abc.jsonl"
            assert transcript.read_text() == '{"type": "user"}\n'
            assert daemon.containers == []
            assert temp_dirs(temp) == []

        async def it_raises_a_timeout_with_the_exit_code_only(
            talker: Botbox, daemon: Daemon, temp: Path, tmp_path: Path
        ) -> None:
            with pytest.raises(Timeout) as raised:
                async with Botbox(talker.agent, timeout=2).session(output=tmp_path) as live:
                    await live.message("hang")
            assert raised.value.result == RunResult(-1)
            assert '"said": "hang"' in (tmp_path / "stdout.txt").read_text()
            assert daemon.containers == []
            assert temp_dirs(temp) == []

    def describe_the_containers() -> None:
        async def it_attaches_to_the_session_command_named_and_labelled_by_the_run_token(
            talker: Botbox, daemon: Daemon
        ) -> None:
            async with talker.session():
                pass
            [proxy] = daemon.runs("botbox-proxy-")
            [agent] = daemon.runs("botbox-agent-")
            run = token(daemon)
            assert option(agent, "--label") == option(proxy, "--label") == f"botbox.run={run}"
            assert "--interactive" in agent
            assert "--rm" not in agent
            assert option(agent, "--pid") == f"container:botbox-proxy-{run}"
            assert agent[-1] == SESSION

        async def it_removes_both_and_the_temp_home_once_the_block_ends(
            talker: Botbox, daemon: Daemon, temp: Path
        ) -> None:
            async with talker.session() as live:
                await live.message("hi")
            run = token(daemon)
            assert daemon.removed == [f"botbox-agent-{run}", f"botbox-proxy-{run}"]
            assert daemon.containers == []
            assert daemon.volumes == []
            assert temp_dirs(temp) == []

    def describe_failure() -> None:
        async def it_refuses_an_agent_with_no_session_mode(daemon: Daemon) -> None:
            with pytest.raises(NotImplementedError, match="no session mode"):
                async with Botbox(CodexAgent()).session():
                    pass
            assert daemon.calls == []

        async def it_raises_when_the_container_never_ran(
            box: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            daemon.agent(SESSION, missing=True)
            with pytest.raises(DockerException) as raised:
                async with box.session(output=output) as live:
                    assert await live.message("hi") == []
            assert raised.value.return_code == 125
            assert "Unable to find image" in raised.value.stderr
            assert "Unable to find image" in (output / "stderr.txt").read_text()
            assert box.result is not None
            assert box.result.exit_code == -1
            assert daemon.containers == []
            assert temp_dirs(temp) == []

        async def it_tears_down_and_raises_when_the_block_fails(
            talker: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            with pytest.raises(ValueError, match="boom"):
                async with talker.session(output=output) as live:
                    await live.message("hi")
                    raise ValueError("boom")
            assert talker.result == RunResult(-1)
            assert_left(output, "hi")
            assert daemon.containers == []
            assert temp_dirs(temp) == []

    def describe_cancelling() -> None:
        async def it_tears_the_session_down_when_cancelled_mid_turn(
            talker: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            heard: list[object] = []
            spoke = asyncio.Event()

            async def talk() -> None:
                async with talker.session(output=output) as live:
                    async for event in live.stream("hang"):
                        heard.append(event)
                        spoke.set()

            task = asyncio.ensure_future(talk())
            await daemon.hanging()
            # The fake flags itself hanging before the loop may have read the event it printed.
            async with asyncio.timeout(10):
                await spoke.wait()
            task.cancel()
            await asyncio.wait({task}, timeout=10)
            assert task.cancelled()
            assert talker.result == RunResult(-1)
            assert_left(output, "hang")
            assert heard == [{"type": "assistant", "said": "hang"}]
            assert daemon.containers == []
            assert temp_dirs(temp) == []

        async def it_finishes_tearing_down_through_a_second_cancel(
            talker: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            daemon.set(rm_seconds=0.3)

            async def talk() -> None:
                async with talker.session(output=output) as live:
                    await live.message("hang")

            task = asyncio.ensure_future(talk())
            await daemon.hanging()
            task.cancel()
            await asyncio.sleep(0.1)
            task.cancel()
            await asyncio.wait({task}, timeout=10)
            assert task.cancelled()
            assert talker.result == RunResult(-1)
            assert_left(output, "hang")
            assert daemon.containers == []
            assert temp_dirs(temp) == []

        async def it_tears_the_session_down_when_a_timeout_fires(
            talker: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(1), talker.session(output=output) as live:
                    await live.message("hang")
            assert '"said": "hang"' in stdout(output)
            assert daemon.containers == []
            assert temp_dirs(temp) == []

        async def it_tears_down_and_raises_what_the_session_left_when_its_timeout_runs_out(
            talker: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            box = Botbox(talker.agent, timeout=2)
            with pytest.raises(Timeout) as raised:
                async with box.session(output=output) as live:
                    await live.message("hang")
            assert raised.value.result == box.result == RunResult(-1)
            assert_left(output, "hang")
            assert daemon.containers == []
            assert temp_dirs(temp) == []


def describe_the_agent_user() -> None:
    async def it_is_the_host_user_with_the_staged_home(talker: Botbox, daemon: Daemon) -> None:
        async with Botbox(talker.agent).session() as live:
            await live.message("hi")
        [agent] = daemon.runs("botbox-agent-")
        assert option(agent, "--user") == f"{os.getuid()}:{os.getgid()}"
        assert "HOME=/home/user" in agent
