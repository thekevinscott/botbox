"""`Botbox.session()` against a fake `docker` on PATH that keeps each container's state."""

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fake_docker_test import REFUSAL, Daemon, homes, option, token

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


def describe_session() -> None:
    def describe_a_turn() -> None:
        async def it_streams_the_events_up_to_the_turns_end(output: Path, talker: Botbox) -> None:
            async with talker.session(output=output) as live:
                events = [event async for event in live.stream("hi")]
            assert events == [
                {"type": "assistant", "said": "hi"},
                {"type": "result", "result": "HI"},
            ]

        async def it_collects_a_turn_and_keeps_the_conversation_going(
            output: Path,
            talker: Botbox,
        ) -> None:
            async with talker.session(output=output) as live:
                first = await live.message("one")
                second = await live.message("two")
            assert [turn[-1]["result"] for turn in (first, second)] == ["ONE", "TWO"]

        async def it_skips_the_rest_of_a_turn_left_early(output: Path, talker: Botbox) -> None:
            async with talker.session(output=output) as live:
                async for _ in live.stream("one"):
                    break
                assert (await live.message("two"))[-1] == {"type": "result", "result": "TWO"}

        async def it_ends_a_turn_the_cli_cuts_short_with_what_arrived(
            output: Path,
            talker: Botbox,
        ) -> None:
            with pytest.raises(DockerException) as raised:
                async with talker.session(output=output) as live:
                    events = await live.message("die")
            assert events in ([], [{"type": "assistant", "said": "die"}])
            assert '"said": "die"' in (output / "stdout.txt").read_text()
            assert raised.value.return_code == -9

    def describe_the_result() -> None:
        async def it_leaves_what_the_session_left_once_the_block_ends(
            output: Path, talker: Botbox, daemon: Daemon
        ) -> None:
            daemon.set(proxy_log=REFUSAL)
            async with talker.session(output=output) as live:
                await live.message("hi")
                assert live.result is None
            assert live.result == RunResult(exit_code=0)
            assert (output / "stdout.txt").read_text() == (
                'booting\n{"type": "assistant", "said": "hi"}\n'
                'not json\n{"type": "result", "result": "HI"}\n'
            )
            assert (output / "stderr.txt").read_text() == ""
            assert (output / "proxy/tinyproxy.log").read_text() == REFUSAL
            assert (output / "transcripts/-work/abc.jsonl").read_text() == '{"type": "user"}\n'

        async def it_reads_the_exit_code_from_the_stopped_container(
            output: Path, box: Botbox, daemon: Daemon
        ) -> None:
            daemon.agent(SESSION, mode="session", exit=3)
            async with box.session(output=output) as live:
                pass
            assert live.result is not None
            assert live.result.exit_code == 3

        async def it_returns_the_result_and_warns_when_teardown_fails(
            output: Path, talker: Botbox, daemon: Daemon
        ) -> None:
            daemon.set(rm_fails=True)
            with pytest.warns(RuntimeWarning) as warned:
                async with talker.session(output=output) as live:
                    await live.message("hi")
            assert live.result is not None
            assert live.result.exit_code == 0
            assert [str(w.message).split(":")[0] for w in warned] == [
                f"botbox could not remove its agent container botbox-agent-{token(daemon)}",
                f"botbox could not remove its proxy botbox-proxy-{token(daemon)}",
            ]

    def describe_the_containers() -> None:
        async def it_attaches_to_the_session_command_named_and_labelled_by_the_run_token(
            output: Path, talker: Botbox, daemon: Daemon
        ) -> None:
            async with talker.session(output=output):
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
            output: Path, talker: Botbox, daemon: Daemon, temp: Path
        ) -> None:
            async with talker.session(output=output) as live:
                await live.message("hi")
            run = token(daemon)
            assert daemon.removed == [f"botbox-agent-{run}", f"botbox-proxy-{run}"]
            assert daemon.containers == []
            assert homes(temp) == []

    def describe_failure() -> None:
        async def it_refuses_an_agent_with_no_session_mode(output: Path, daemon: Daemon) -> None:
            with pytest.raises(NotImplementedError, match="no session mode"):
                async with Botbox(CodexAgent()).session(output=output):
                    pass
            assert daemon.calls == []

        async def it_raises_when_the_container_never_ran(
            output: Path, box: Botbox, daemon: Daemon, temp: Path
        ) -> None:
            daemon.agent(SESSION, missing=True)
            with pytest.raises(DockerException) as raised:
                async with box.session(output=output) as live:
                    assert await live.message("hi") == []
            assert raised.value.return_code == 125
            assert "Unable to find image" in (output / "stderr.txt").read_text()
            assert live.result is not None
            assert live.result.exit_code == -1
            assert daemon.containers == []
            assert homes(temp) == []

        @pytest.mark.usefixtures("unreadable_transcript")
        async def it_preserves_the_original_error_if_artifact_reading_fails(
            output: Path,
            talker: Botbox,
            daemon: Daemon,
            temp: Path,
        ) -> None:
            failed = ValueError("original failure")
            with (
                pytest.raises(ValueError) as raised,
            ):
                async with talker.session(output=output) as live:
                    await live.message("hi")
                    raise failed
            assert raised.value is failed
            assert daemon.containers == []
            assert homes(temp) == []

        async def it_tears_down_and_raises_when_the_block_fails(
            output: Path, talker: Botbox, daemon: Daemon, temp: Path
        ) -> None:
            with pytest.raises(ValueError, match="boom"):
                async with talker.session(output=output) as live:
                    await live.message("hi")
                    raise ValueError("boom")
            assert live.result is not None
            assert live.result.exit_code == -1
            assert {
                f".claude/projects/{p.relative_to(output / 'transcripts')}": p.read_text()
                for p in (output / "transcripts").rglob("*.jsonl")
            }
            assert '"said": "hi"' in (output / "stdout.txt").read_text()
            assert daemon.containers == []
            assert homes(temp) == []

    def describe_cancelling() -> None:
        async def it_tears_the_session_down_when_cancelled_mid_turn(
            output: Path, talker: Botbox, daemon: Daemon, temp: Path
        ) -> None:
            heard: list[object] = []
            spoke = asyncio.Event()

            sessions: list[Session] = []

            async def talk() -> None:
                async with talker.session(output=output) as live:
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
            assert {
                f".claude/projects/{p.relative_to(output / 'transcripts')}": p.read_text()
                for p in (output / "transcripts").rglob("*.jsonl")
            }
            assert '"said": "hang"' in (output / "stdout.txt").read_text()
            assert heard == [{"type": "assistant", "said": "hang"}]
            assert daemon.containers == []
            assert homes(temp) == []

        async def it_finishes_tearing_down_through_a_second_cancel(
            output: Path, talker: Botbox, daemon: Daemon, temp: Path
        ) -> None:
            daemon.set(rm_seconds=0.3)

            sessions: list[Session] = []

            async def talk() -> None:
                async with talker.session(output=output) as live:
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
            assert {
                f".claude/projects/{p.relative_to(output / 'transcripts')}": p.read_text()
                for p in (output / "transcripts").rglob("*.jsonl")
            }
            assert '"said": "hang"' in (output / "stdout.txt").read_text()
            assert daemon.containers == []
            assert homes(temp) == []

        async def it_tears_the_session_down_when_a_timeout_fires(
            output: Path, talker: Botbox, daemon: Daemon, temp: Path
        ) -> None:
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(1), talker.session(output=output) as live:
                    await live.message("hang")
            assert daemon.containers == []
            assert homes(temp) == []

        async def it_tears_down_and_raises_what_the_session_left_when_its_timeout_runs_out(
            output: Path, talker: Botbox, daemon: Daemon, temp: Path
        ) -> None:
            sessions: list[Session] = []
            with pytest.raises(Timeout) as raised:
                async with Botbox(talker.agent, timeout=2).session(output=output) as live:
                    sessions.append(live)
                    await live.message("hang")
            result = raised.value.result
            assert result is sessions[0].result
            assert result.exit_code == -1
            assert {
                f".claude/projects/{p.relative_to(output / 'transcripts')}": p.read_text()
                for p in (output / "transcripts").rglob("*.jsonl")
            }
            assert '"said": "hang"' in (output / "stdout.txt").read_text()
            assert daemon.containers == []
            assert homes(temp) == []


def describe_the_agent_user() -> None:
    async def it_is_the_host_user_with_the_staged_home(
        output: Path, talker: Botbox, daemon: Daemon
    ) -> None:
        async with Botbox(talker.agent).session(output=output) as live:
            await live.message("hi")
        [agent] = daemon.runs("botbox-agent-")
        assert option(agent, "--user") == f"{os.getuid()}:{os.getgid()}"
        assert "HOME=/home/user" in agent
