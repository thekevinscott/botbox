"""`Botbox.session()` against a fake `docker` on PATH that keeps each container's state."""

import asyncio
import os
from pathlib import Path

import pytest
from fake_docker_test import (
    LISTENING,
    REFUSAL,
    CopyingClaude,
    Daemon,
    option,
    temp_dirs,
    token,
)

from botbox import (
    Agent,
    Botbox,
    ClaudeAgent,
    CodexAgent,
    DockerException,
    Message,
    RunResult,
    Timeout,
)

SESSION = ClaudeAgent().session_command()


@pytest.fixture
def output(tmp_path: Path) -> Path:
    return tmp_path / "output"


def assert_left(output: Path, said: str) -> None:
    """The session's stdout and transcript are in `output`."""
    assert f'"text": "{said}"' in (output / "stdout.txt").read_text()
    assert (output / "transcripts" / "-work" / "abc.jsonl").is_file()


@pytest.fixture
def talker(box: Botbox, daemon: Daemon) -> Botbox:
    """The box, its agent's session planned to answer each message."""
    daemon.agent(SESSION, mode="session", stdout="booting\n")
    return box


def stdout(output: Path) -> str:
    return (output / "stdout.txt").read_text()


async def ask(agent: Agent, text: str) -> str:
    """Send `text` and return the reply's text, opening the replies first so none is missed."""
    replies = agent.replies
    await agent.send(text)
    return (await anext(replies)).text


def kinds(messages: list[Message]) -> list[tuple[str, str]]:
    return [(message.type, message.text) for message in messages]


async def hang(agent: Agent) -> None:
    """Send the message the fake CLI hangs on, and read until its stdout ends."""
    messages = agent.messages
    await agent.send("hang")
    async for _ in messages:
        pass


async def hear(agent: Agent, text: str) -> list[Message]:
    """Send `text` and return every message until the CLI's stdout ends."""
    messages = agent.messages
    await agent.send(text)
    return [message async for message in messages]


ONE = [("assistant", ""), ("user", ""), ("assistant", "one")]


def describe_session() -> None:
    def describe_messages() -> None:
        async def it_yields_the_agent_to_send_to_and_hear_from(
            talker: Botbox, output: Path
        ) -> None:
            async with talker.session(output=output) as agent:
                assert agent is talker.agent
                assert await ask(agent, "one") == "one"
                assert await ask(agent, "two") == "two"

        async def it_hears_every_message_with_its_type_text_and_event(
            talker: Botbox, output: Path
        ) -> None:
            async with talker.session(output=output) as agent:
                messages = agent.messages
                await agent.send("one")
                heard = [await anext(messages) for _ in range(3)]
            assert kinds(heard) == ONE
            assert heard[0].type == ClaudeAgent.MESSAGE_TYPE.ASSISTANT
            assert heard[2].event == {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "one"}]},
            }

        async def it_replies_only_with_the_agents_messages_that_have_text(
            talker: Botbox, output: Path
        ) -> None:
            async with talker.session(output=output) as agent:
                replies = agent.replies
                await agent.send("one")
                await agent.send("two")
                assert [(await anext(replies)).text for _ in range(2)] == ["one", "two"]

        async def it_gives_each_reader_every_message_from_when_it_opened(
            talker: Botbox, output: Path
        ) -> None:
            async with talker.session(output=output) as agent:
                first = agent.messages
                await agent.send("one")
                assert kinds([await anext(first) for _ in range(3)]) == ONE
                second = agent.messages
                await agent.send("two")
                for messages in (first, second):
                    assert [(await anext(messages)).text for _ in range(3)] == ["", "", "two"]

        async def it_ends_each_reader_when_the_cli_exits(talker: Botbox, output: Path) -> None:
            async with talker.session(output=output) as agent:
                messages = agent.messages
                await agent.send("one")
                agent.channel.stdin.close()  # type: ignore[union-attr]
                assert kinds([message async for message in messages]) == ONE
                assert [message async for message in agent.replies] == []

        async def it_calls_back_with_each_reply_and_message(talker: Botbox, output: Path) -> None:
            replies: list[str] = []
            messages: list[str] = []
            async with talker.session(output=output) as agent:
                agent.on("reply", lambda reply: replies.append(reply.text))
                agent.on("message", lambda message: messages.append(message.type))
                assert await ask(agent, "one") == "one"
            assert replies == ["one"]
            assert messages == ["assistant", "user", "assistant"]

        async def it_ends_the_session_with_a_callback_that_raises(
            talker: Botbox, output: Path
        ) -> None:
            def fail(_reply: Message) -> None:
                raise ValueError("callback")

            with pytest.raises(ValueError, match="callback"):
                async with talker.session(output=output) as agent:
                    agent.on("reply", fail)
                    messages = agent.messages
                    await agent.send("one")
                    assert kinds([message async for message in messages]) == ONE
            assert agent.result == RunResult(-1)

        async def it_lets_two_agents_talk(daemon: Daemon, tmp_path: Path) -> None:
            daemon.agent(SESSION, mode="session")
            home = tmp_path / "claude-home"
            alice = Botbox(CopyingClaude(api_key="sk-test", host_home=home))
            bob = Botbox(CopyingClaude(api_key="sk-test", host_home=home))
            async with (
                alice.session(output=tmp_path / "a") as a,
                bob.session(output=tmp_path / "b") as b,
            ):
                heard = b.replies
                await b.send(await ask(a, "plan"))
                assert (await anext(heard)).text == "plan"

        async def it_refuses_to_send_once_the_session_is_over(talker: Botbox) -> None:
            async with talker.session() as agent:
                pass
            with pytest.raises(RuntimeError, match="no session open"):
                await agent.send("hi")

        async def it_reads_messages_past_a_large_line_that_is_not_one(
            box: Botbox, daemon: Daemon, output: Path
        ) -> None:
            large = "x" * (1 << 20) + "\n"
            daemon.agent(SESSION, mode="session", stdout=large)
            async with box.session(output=output) as agent:
                assert await ask(agent, "hi") == "hi"
            assert stdout(output).startswith(large)

        async def it_reads_a_message_far_past_a_pipe_chunk(talker: Botbox, output: Path) -> None:
            large = "x" * (16 << 20)
            async with talker.session(output=output) as agent:
                assert await ask(agent, large) == large
            assert f'"text": "{large}"' in stdout(output)

        async def it_hears_what_arrived_from_a_cli_cut_short(talker: Botbox, output: Path) -> None:
            heard: list[Message] = []
            with pytest.raises(DockerException) as raised:
                async with talker.session(output=output) as agent:
                    messages = agent.messages
                    await agent.send("die")
                    heard.extend([message async for message in messages])
            assert kinds(heard) == [("assistant", ""), ("user", ""), ("assistant", "die")]
            assert raised.value.return_code == -9

    def describe_the_result() -> None:
        async def it_leaves_only_the_exit_code_once_the_block_ends(talker: Botbox) -> None:
            async with talker.session() as live:
                await ask(live, "hi")
                assert live.result is None
            assert live.result == RunResult(0, oom_killed=False)

        async def it_reads_the_exit_code_from_the_stopped_container(
            box: Botbox, daemon: Daemon, output: Path
        ) -> None:
            daemon.agent(SESSION, mode="session", exit=3)
            async with box.session(output=output) as live:
                pass
            assert live.result is not None
            assert live.result.exit_code == 3

        async def it_returns_the_result_and_warns_when_teardown_fails(
            talker: Botbox, daemon: Daemon, output: Path
        ) -> None:
            daemon.set(rm_fails=True)
            with pytest.warns(RuntimeWarning) as warned:
                async with talker.session(output=output) as live:
                    await ask(live, "hi")
            assert live.result is not None
            assert live.result.exit_code == 0
            assert [str(w.message).split(":")[0] for w in warned] == [
                f"botbox could not remove its agent container botbox-agent-{token(daemon)}",
                f"botbox could not remove its proxy botbox-proxy-{token(daemon)}",
            ]

    def describe_output() -> None:
        async def it_streams_events_whatever_happens_to_the_output_file(
            talker: Botbox, output: Path
        ) -> None:
            async with talker.session(output=output) as live:
                first = await ask(live, "one")
                (output / "stdout.txt").write_bytes(b"")
                second = await ask(live, "two")
            assert first == "one"
            assert second == "two"
            assert live.result == RunResult(0, oom_killed=False)

        async def it_drops_an_output_file_that_fails_and_carries_on(
            talker: Botbox, output: Path
        ) -> None:
            output.mkdir()
            (output / "stdout.txt").symlink_to("/dev/full")
            with pytest.warns(RuntimeWarning, match="stopped writing to .*stdout.txt"):
                async with talker.session(output=output) as live:
                    reply = await ask(live, "one")
            assert reply == "one"
            assert live.result == RunResult(0, oom_killed=False)
            assert (output / "stderr.txt").is_file()

        async def it_leaves_nothing_behind_without_output(talker: Botbox, temp: Path) -> None:
            async with talker.session() as live:
                assert await ask(live, "one") == "one"
            assert live.result == RunResult(0, oom_killed=False)
            assert list(temp.iterdir()) == []

        async def it_writes_what_it_streams_to_the_output(
            talker: Botbox, daemon: Daemon, temp: Path, tmp_path: Path
        ) -> None:
            daemon.agent(SESSION, mode="session", stdout="booting\n", stderr="diagnostic\n")
            daemon.set(proxy_log=REFUSAL)
            output = tmp_path / "output"
            async with talker.session(output=output) as live:
                first = await ask(live, "one")
                second = await ask(live, "two")
            assert first == "one"
            assert second == "two"
            assert live.result == RunResult(0, oom_killed=False)
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
                    assert await hear(live, "hi") == []
            assert "Unable to find image" in raised.value.stderr
            assert (tmp_path / "stderr.txt").read_text() == raised.value.stderr

        async def it_ends_a_turn_the_cli_cuts_short_and_leaves_the_files(
            talker: Botbox, daemon: Daemon, temp: Path, tmp_path: Path
        ) -> None:
            with pytest.raises(DockerException) as raised:
                async with talker.session(output=tmp_path) as live:
                    events = await hear(live, "die")
            assert kinds(events) == [("assistant", ""), ("user", ""), ("assistant", "die")]
            assert raised.value.return_code == -9
            assert raised.value.stderr == ""
            assert live.result == RunResult(-1)
            assert '"text": "die"' in (tmp_path / "stdout.txt").read_text()
            assert daemon.containers == []
            assert temp_dirs(temp) == []

        async def it_tears_down_when_cancelled_mid_turn(
            talker: Botbox, daemon: Daemon, temp: Path, tmp_path: Path
        ) -> None:
            sessions: list[Agent] = []

            async def talk() -> None:
                async with talker.session(output=tmp_path) as live:
                    sessions.append(live)
                    await hang(live)

            task = asyncio.ensure_future(talk())
            await daemon.hanging()
            task.cancel()
            await asyncio.wait({task}, timeout=10)
            assert task.cancelled()
            assert sessions[0].result == RunResult(-1)
            assert '"text": "hang"' in (tmp_path / "stdout.txt").read_text()
            transcript = tmp_path / "transcripts" / "-work" / "abc.jsonl"
            assert transcript.read_text() == '{"type": "user"}\n'
            assert daemon.containers == []
            assert temp_dirs(temp) == []

        async def it_raises_a_timeout_with_the_exit_code_only(
            talker: Botbox, daemon: Daemon, temp: Path, tmp_path: Path
        ) -> None:
            with pytest.raises(Timeout) as raised:
                async with Botbox(talker.agent, timeout=2).session(output=tmp_path) as live:
                    await hang(live)
            assert raised.value.result == RunResult(-1)
            assert '"text": "hang"' in (tmp_path / "stdout.txt").read_text()
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
                await ask(live, "hi")
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
                    assert await hear(live, "hi") == []
            assert raised.value.return_code == 125
            assert "Unable to find image" in raised.value.stderr
            assert "Unable to find image" in (output / "stderr.txt").read_text()
            assert live.result is not None
            assert live.result.exit_code == -1
            assert daemon.containers == []
            assert temp_dirs(temp) == []

        async def it_tears_down_and_raises_when_the_block_fails(
            talker: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            with pytest.raises(ValueError, match="boom"):
                async with talker.session(output=output) as live:
                    await ask(live, "hi")
                    raise ValueError("boom")
            assert live.result == RunResult(-1)
            assert_left(output, "hi")
            assert daemon.containers == []
            assert temp_dirs(temp) == []

    def describe_cancelling() -> None:
        async def it_tears_the_session_down_when_cancelled_mid_turn(
            talker: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            heard: list[Message] = []
            spoke = asyncio.Event()

            sessions: list[Agent] = []

            async def talk() -> None:
                async with talker.session(output=output) as live:
                    sessions.append(live)
                    messages = live.messages
                    await live.send("hang")
                    async for message in messages:
                        heard.append(message)
                        if message.text:
                            spoke.set()

            task = asyncio.ensure_future(talk())
            await daemon.hanging()
            # The fake flags itself hanging before the loop may have read the message it printed.
            async with asyncio.timeout(10):
                await spoke.wait()
            task.cancel()
            await asyncio.wait({task}, timeout=10)
            assert task.cancelled()
            assert sessions[0].result == RunResult(-1)
            assert_left(output, "hang")
            assert kinds(heard) == [("assistant", ""), ("user", ""), ("assistant", "hang")]
            assert daemon.containers == []
            assert temp_dirs(temp) == []

        async def it_finishes_tearing_down_through_a_second_cancel(
            talker: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            daemon.set(rm_seconds=0.3)

            sessions: list[Agent] = []

            async def talk() -> None:
                async with talker.session(output=output) as live:
                    sessions.append(live)
                    await hang(live)

            task = asyncio.ensure_future(talk())
            await daemon.hanging()
            task.cancel()
            await asyncio.sleep(0.1)
            task.cancel()
            await asyncio.wait({task}, timeout=10)
            assert task.cancelled()
            assert sessions[0].result == RunResult(-1)
            assert_left(output, "hang")
            assert daemon.containers == []
            assert temp_dirs(temp) == []

        async def it_tears_the_session_down_when_a_timeout_fires(
            talker: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(1), talker.session(output=output) as live:
                    await hang(live)
            assert '"text": "hang"' in stdout(output)
            assert daemon.containers == []
            assert temp_dirs(temp) == []

        async def it_tears_down_and_raises_what_the_session_left_when_its_timeout_runs_out(
            talker: Botbox, daemon: Daemon, temp: Path, output: Path
        ) -> None:
            sessions: list[Agent] = []
            with pytest.raises(Timeout) as raised:
                async with Botbox(talker.agent, timeout=2).session(output=output) as live:
                    sessions.append(live)
                    await hang(live)
            assert raised.value.result == sessions[0].result == RunResult(-1)
            assert_left(output, "hang")
            assert daemon.containers == []
            assert temp_dirs(temp) == []


def describe_the_agent_user() -> None:
    async def it_is_the_host_user_with_the_staged_home(talker: Botbox, daemon: Daemon) -> None:
        async with Botbox(talker.agent).session() as live:
            await ask(live, "hi")
        [agent] = daemon.runs("botbox-agent-")
        assert option(agent, "--user") == f"{os.getuid()}:{os.getgid()}"
        assert "HOME=/home/user" in agent
