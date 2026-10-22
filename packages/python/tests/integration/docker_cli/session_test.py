"""`Botbox.session()` against a fake `docker` on PATH that keeps each container's state."""

import asyncio
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fake_docker_test import REFUSAL, Daemon, homes, option, token

from botbox import Botbox, ClaudeAgent, CodexAgent, DockerException, RunResult, Session

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
                proxy=REFUSAL,
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

            sessions: list[Session] = []

            async def talk() -> None:
                async with talker.session() as live:
                    sessions.append(live)
                    async for event in live.stream("hang"):
                        heard.append(event)

            task = asyncio.ensure_future(talk())
            await daemon.hanging()
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
