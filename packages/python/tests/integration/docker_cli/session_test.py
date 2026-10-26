"""`Botbox.session()` against a fake `docker` on PATH that keeps each container's state."""

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fake_docker_test import LISTENING, REFUSAL, Daemon, homes, option, token

from botbox import (
    Botbox,
    ClaudeAgent,
    CodexAgent,
    DockerException,
    RunResult,
    Session,
    Timeout,
)

SESSION = ClaudeAgent().session_command()


@pytest.fixture
def talker(box: Botbox, daemon: Daemon) -> Botbox:
    """The box, its agent's session planned to answer each message."""
    daemon.agent(SESSION, mode="session", stdout="booting\n")
    return box


@pytest.fixture
def unreadable_transcript() -> Iterator[Mock]:
    original = Path.glob

    def glob(path: Path, pattern: str) -> Iterator[Path]:
        if path.name == "home":
            raise OSError("unreadable transcript directory")
        return original(path, pattern)

    with patch("pathlib.Path.glob", autospec=True, side_effect=glob) as read:
        yield read


def followers(path: Path) -> list[str]:
    """Processes still running with `path` on their command line."""
    found = []
    for proc in Path("/proc").iterdir():
        try:
            cmdline = (proc / "cmdline").read_bytes()
        except OSError:
            continue
        if str(path).encode() in cmdline.split(b"\0"):
            found.append(cmdline.replace(b"\0", b" ").decode(errors="replace"))
    return found


def describe_session() -> None:
    def describe_a_turn() -> None:
        async def it_streams_the_events_up_to_the_turns_end(talker: Botbox) -> None:
            async with talker.session() as live:
                events = [event async for event in live.stream("hi")]
            assert events == [
                {"type": "assistant", "said": "hi"},
                {"type": "result", "result": "HI"},
            ]

        async def it_collects_a_turn_and_keeps_the_conversation_going(
            talker: Botbox,
        ) -> None:
            async with talker.session() as live:
                first = await live.message("one")
                second = await live.message("two")
            assert [turn[-1]["result"] for turn in (first, second)] == ["ONE", "TWO"]

        async def it_skips_the_rest_of_a_turn_left_early(talker: Botbox) -> None:
            async with talker.session() as live:
                async for _ in live.stream("one"):
                    break
                assert (await live.message("two"))[-1] == {"type": "result", "result": "TWO"}

        async def it_ends_a_turn_the_cli_cuts_short_with_what_arrived(
            talker: Botbox,
        ) -> None:
            with pytest.raises(DockerException) as raised:
                async with talker.session() as live:
                    events = await live.message("die")
            assert events == [{"type": "assistant", "said": "die"}]
            assert raised.value.return_code == -9

    def describe_the_result() -> None:
        async def it_leaves_what_the_session_left_once_the_block_ends(
            talker: Botbox, daemon: Daemon
        ) -> None:
            daemon.set(proxy_log=REFUSAL)
            async with talker.session() as live:
                await live.message("hi")
                assert live.result is None
            assert live.result == RunResult(
                stdout=(
                    "booting\n"
                    '{"type": "assistant", "said": "hi"}\n'
                    "not json\n"
                    '{"type": "result", "result": "HI"}\n'
                ),
                stderr="",
                exit_code=0,
                transcript={".claude/projects/-work/abc.jsonl": '{"type": "user"}\n'},
                proxy=LISTENING + REFUSAL,
                image="botbox-claude:latest",
            )

        async def it_reads_the_exit_code_from_the_stopped_container(
            box: Botbox, daemon: Daemon
        ) -> None:
            daemon.agent(SESSION, mode="session", exit=3)
            async with box.session() as live:
                pass
            assert live.result is not None
            assert live.result.exit_code == 3

        async def it_returns_the_result_and_warns_when_teardown_fails(
            talker: Botbox, daemon: Daemon
        ) -> None:
            daemon.set(rm_fails=True)
            with pytest.warns(RuntimeWarning) as warned:
                async with talker.session() as live:
                    await live.message("hi")
            assert live.result is not None
            assert live.result.exit_code == 0
            assert [str(w.message).split(":")[0] for w in warned] == [
                f"botbox could not remove its agent container botbox-agent-{token(daemon)}",
                f"botbox could not remove its proxy botbox-proxy-{token(daemon)}",
            ]

    def describe_output() -> None:
        async def it_streams_events_from_the_files_it_writes(
            talker: Botbox, daemon: Daemon, temp: Path, tmp_path: Path
        ) -> None:
            daemon.set(proxy_log=REFUSAL)
            output = tmp_path / "output"
            async with talker.session(output=output) as live:
                first = await live.message("one")
                second = await live.message("two")
                assert followers(output / "stdout.txt")
            assert first[-1] == {"type": "result", "result": "ONE"}
            assert second[-1] == {"type": "result", "result": "TWO"}
            assert live.result == RunResult("", "", 0, {}, "", "botbox-claude:latest")
            stdout = (output / "stdout.txt").read_text()
            assert stdout.startswith("booting\n")
            assert '{"type": "result", "result": "TWO"}\n' in stdout
            transcript = output / "transcripts" / "-work" / "abc.jsonl"
            assert transcript.read_text() == '{"type": "user"}\n'
            assert (output / "proxy.log").read_text() == REFUSAL
            assert followers(output / "stdout.txt") == []
            assert daemon.containers == []
            assert homes(temp) == []

        async def it_points_at_stderr_when_the_container_never_ran(
            box: Botbox, daemon: Daemon, tmp_path: Path
        ) -> None:
            daemon.agent(SESSION, missing=True)
            with pytest.raises(DockerException) as raised:
                async with box.session(output=tmp_path) as live:
                    assert await live.message("hi") == []
            assert raised.value.stderr == f"See {tmp_path / 'stderr.txt'}"
            assert "Unable to find image" in (tmp_path / "stderr.txt").read_text()

        async def it_ends_a_turn_the_cli_cuts_short_and_leaves_the_files(
            talker: Botbox, daemon: Daemon, temp: Path, tmp_path: Path
        ) -> None:
            with pytest.raises(DockerException) as raised:
                async with talker.session(output=tmp_path) as live:
                    events = await live.message("die")
            assert events == [{"type": "assistant", "said": "die"}]
            assert raised.value.return_code == -9
            assert raised.value.stderr == f"See {tmp_path / 'stderr.txt'}"
            assert live.result == RunResult("", "", -1, {}, "", "botbox-claude:latest")
            assert '"said": "die"' in (tmp_path / "stdout.txt").read_text()
            assert followers(tmp_path / "stdout.txt") == []
            assert daemon.containers == []
            assert homes(temp) == []

        async def it_tears_down_when_cancelled_mid_turn(
            talker: Botbox, daemon: Daemon, temp: Path, tmp_path: Path
        ) -> None:
            sessions: list[Session] = []

            async def talk() -> None:
                async with talker.session(output=tmp_path) as live:
                    sessions.append(live)
                    await live.message("hang")

            task = asyncio.ensure_future(talk())
            await daemon.hanging()
            task.cancel()
            await asyncio.wait({task}, timeout=10)
            assert task.cancelled()
            assert sessions[0].result == RunResult("", "", -1, {}, "", "botbox-claude:latest")
            assert '"said": "hang"' in (tmp_path / "stdout.txt").read_text()
            transcript = tmp_path / "transcripts" / "-work" / "abc.jsonl"
            assert transcript.read_text() == '{"type": "user"}\n'
            assert followers(tmp_path / "stdout.txt") == []
            assert daemon.containers == []
            assert homes(temp) == []

        async def it_raises_a_timeout_with_the_exit_code_only(
            talker: Botbox, daemon: Daemon, temp: Path, tmp_path: Path
        ) -> None:
            with pytest.raises(Timeout) as raised:
                async with Botbox(talker.agent, timeout=2).session(output=tmp_path) as live:
                    await live.message("hang")
            assert raised.value.result == RunResult("", "", -1, {}, "", "botbox-claude:latest")
            assert '"said": "hang"' in (tmp_path / "stdout.txt").read_text()
            assert followers(tmp_path / "stdout.txt") == []
            assert daemon.containers == []
            assert homes(temp) == []

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
            assert homes(temp) == []

    def describe_failure() -> None:
        async def it_refuses_an_agent_with_no_session_mode(daemon: Daemon) -> None:
            with pytest.raises(NotImplementedError, match="no session mode"):
                async with Botbox(CodexAgent()).session():
                    pass
            assert daemon.calls == []

        async def it_raises_when_the_container_never_ran(
            box: Botbox, daemon: Daemon, temp: Path
        ) -> None:
            daemon.agent(SESSION, missing=True)
            with pytest.raises(DockerException) as raised:
                async with box.session() as live:
                    assert await live.message("hi") == []
            assert raised.value.return_code == 125
            assert "Unable to find image" in raised.value.stderr
            assert live.result is not None
            assert live.result.exit_code == -1
            assert daemon.containers == []
            assert homes(temp) == []

        @pytest.mark.usefixtures("unreadable_transcript")
        async def it_preserves_the_original_error_if_artifact_reading_fails(
            talker: Botbox,
            daemon: Daemon,
            temp: Path,
        ) -> None:
            failed = ValueError("original failure")
            with (
                pytest.warns(RuntimeWarning, match="read its session artifacts"),
                pytest.raises(ValueError) as raised,
            ):
                async with talker.session() as live:
                    await live.message("hi")
                    raise failed
            assert raised.value is failed
            assert daemon.containers == []
            assert homes(temp) == []

        async def it_tears_down_and_raises_when_the_block_fails(
            talker: Botbox, daemon: Daemon, temp: Path
        ) -> None:
            with pytest.raises(ValueError, match="boom"):
                async with talker.session() as live:
                    await live.message("hi")
                    raise ValueError("boom")
            assert live.result is not None
            assert live.result.exit_code == -1
            assert live.result.transcript
            assert '"said": "hi"' in live.result.stdout
            assert daemon.containers == []
            assert homes(temp) == []

    def describe_cancelling() -> None:
        async def it_tears_the_session_down_when_cancelled_mid_turn(
            talker: Botbox, daemon: Daemon, temp: Path
        ) -> None:
            heard: list[object] = []
            spoke = asyncio.Event()

            sessions: list[Session] = []

            async def talk() -> None:
                async with talker.session() as live:
                    sessions.append(live)
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
            result = sessions[0].result
            assert result is not None
            assert result.exit_code == -1
            assert result.transcript
            assert '"said": "hang"' in result.stdout
            assert heard == [{"type": "assistant", "said": "hang"}]
            assert daemon.containers == []
            assert homes(temp) == []

        async def it_finishes_tearing_down_through_a_second_cancel(
            talker: Botbox, daemon: Daemon, temp: Path
        ) -> None:
            daemon.set(rm_seconds=0.3)

            sessions: list[Session] = []

            async def talk() -> None:
                async with talker.session() as live:
                    sessions.append(live)
                    await live.message("hang")

            task = asyncio.ensure_future(talk())
            await daemon.hanging()
            task.cancel()
            await asyncio.sleep(0.1)
            task.cancel()
            await asyncio.wait({task}, timeout=10)
            assert task.cancelled()
            result = sessions[0].result
            assert result is not None
            assert result.exit_code == -1
            assert result.transcript
            assert '"said": "hang"' in result.stdout
            assert daemon.containers == []
            assert homes(temp) == []

        async def it_tears_the_session_down_when_a_timeout_fires(
            talker: Botbox, daemon: Daemon, temp: Path
        ) -> None:
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(1), talker.session() as live:
                    await live.message("hang")
            assert daemon.containers == []
            assert homes(temp) == []

        async def it_tears_down_and_raises_what_the_session_left_when_its_timeout_runs_out(
            talker: Botbox, daemon: Daemon, temp: Path
        ) -> None:
            sessions: list[Session] = []
            with pytest.raises(Timeout) as raised:
                async with Botbox(talker.agent, timeout=2).session() as live:
                    sessions.append(live)
                    await live.message("hang")
            result = raised.value.result
            assert result is sessions[0].result
            assert result.exit_code == -1
            assert result.transcript
            assert '"said": "hang"' in result.stdout
            assert daemon.containers == []
            assert homes(temp) == []


def describe_the_agent_user() -> None:
    async def it_is_the_host_user_with_the_staged_home(talker: Botbox, daemon: Daemon) -> None:
        async with Botbox(talker.agent).session() as live:
            await live.message("hi")
        [agent] = daemon.runs("botbox-agent-")
        assert option(agent, "--user") == f"{os.getuid()}:{os.getgid()}"
        assert "HOME=/home/user" in agent
