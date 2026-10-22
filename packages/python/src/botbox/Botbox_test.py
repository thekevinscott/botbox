import argparse
import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from botbox.Botbox import Botbox

AGENT_STEP = Mock(
    context=Path("/agents"),
    tag="an-agent:latest",
    file=Path("/agents/D"),
    contexts={"botbox": "/r"},
)
LAYER_STEP = Mock(
    context=Path("/consumer"), tag="an-agent-123:latest", file=Path("/consumer/D"), contexts={}
)


@pytest.fixture
def agent() -> Mock:
    return Mock(image="an-agent:latest")


@pytest.fixture
def layer(tmp_path: Path) -> Path:
    return tmp_path / "consumer" / "Dockerfile"


@pytest.fixture
def steps() -> list[str]:
    """Each lock taken and released, and each build, in order."""
    return []


@pytest.fixture(autouse=True)
def build_steps() -> Iterator[Mock]:
    with patch("botbox.Botbox.build_steps", autospec=True) as m:
        m.return_value = [AGENT_STEP, LAYER_STEP]
        yield m


@pytest.fixture(autouse=True)
def docker_build(steps: list[str]) -> Iterator[Mock]:
    async def build(_context: Path, *, tag: str, **_options: Any) -> None:
        steps.append(f"build {tag}")

    with patch("botbox.Botbox.docker_build", autospec=True, side_effect=build) as m:
        yield m


class CommandFailed(Exception):
    """Stands in for the SDK's `DockerException`."""


@pytest.fixture(autouse=True)
def lock(steps: list[str]) -> Iterator[None]:
    @asynccontextmanager
    async def lock(tag: str) -> AsyncIterator[None]:
        steps.append(f"lock {tag}")
        try:
            yield
        finally:
            steps.append(f"unlock {tag}")

    with patch("botbox.Botbox.build_lock", lock):
        yield


def send_sigterm(handlers: Mock) -> None:
    """Call the SIGTERM handler the box added to the loop."""
    [(_, handler, *args)] = [c.args for c in handlers.add.call_args_list]
    handler(*args)


def describe_botbox() -> None:
    def it_keeps_the_agent(agent: Mock) -> None:
        assert Botbox(agent).agent is agent

    def it_takes_its_options_by_keyword_only(agent: Mock, layer: Path) -> None:
        with pytest.raises(TypeError):
            Botbox(agent, layer)  # type: ignore[call-arg]

    def it_has_no_dockerfile_by_default(agent: Mock) -> None:
        assert Botbox(agent).dockerfile is None

    def it_holds_the_dockerfile_as_an_absolute_path(agent: Mock, layer: Path) -> None:
        assert Botbox(agent, dockerfile=str(layer)).dockerfile == layer

    def it_allows_nothing_extra_by_default(agent: Mock) -> None:
        assert Botbox(agent).allow == ()

    def it_holds_the_extra_hosts_as_a_tuple(agent: Mock) -> None:
        assert Botbox(agent, allow=["registry.npmjs.org"]).allow == ("registry.npmjs.org",)

    def it_refuses_a_bare_string_that_would_split_into_characters(agent: Mock) -> None:
        with pytest.raises(TypeError, match=r"allow=\('github\.com',\)"):
            Botbox(agent, allow="github.com")

    def it_caps_each_output_stream_at_100_gib_by_default(agent: Mock) -> None:
        box = Botbox(agent)
        assert box.stdout_limit == box.stderr_limit == 100 * 2**30

    def it_holds_the_output_caps_it_is_given(agent: Mock) -> None:
        box = Botbox(agent, stdout_limit=2**20, stderr_limit=0)
        assert (box.stdout_limit, box.stderr_limit) == (2**20, 0)

    def it_refuses_a_negative_stdout_cap(agent: Mock) -> None:
        with pytest.raises(ValueError, match=r"^stdout_limit must be at least 0, got -1$"):
            Botbox(agent, stdout_limit=-1)

    def it_refuses_a_negative_stderr_cap(agent: Mock) -> None:
        with pytest.raises(ValueError, match=r"^stderr_limit must be at least 0, got -2$"):
            Botbox(agent, stderr_limit=-2)

    def describe_sigterm() -> None:
        @pytest.fixture(autouse=True)
        def threads() -> Iterator[MagicMock]:
            with patch("botbox.Botbox.threading", autospec=True) as m:
                m.current_thread.return_value = m.main_thread.return_value
                yield m

        @pytest.fixture(autouse=True)
        def signals() -> Iterator[MagicMock]:
            with patch("botbox.Botbox.signal", autospec=True) as m:
                m.getsignal.return_value = m.SIG_DFL
                yield m

        @pytest.fixture(autouse=True)
        async def handlers() -> AsyncIterator[Mock]:
            """The running loop's signal handlers, added and removed."""
            loop = asyncio.get_running_loop()
            with (
                patch.object(loop, "add_signal_handler") as add,
                patch.object(loop, "remove_signal_handler") as remove,
            ):
                yield Mock(add=add, remove=remove)

        async def it_is_its_own_context(agent: Mock) -> None:
            box = Botbox(agent)
            async with box as entered:
                assert entered is box

        async def it_handles_sigterm_inside_the_block(
            agent: Mock, signals: MagicMock, handlers: Mock
        ) -> None:
            async with Botbox(agent):
                [(signum, *_)] = [c.args for c in handlers.add.call_args_list]
                assert signum is signals.SIGTERM
                handlers.remove.assert_not_called()
            handlers.remove.assert_called_once_with(signals.SIGTERM)

        async def it_cancels_the_block_and_exits_143_on_sigterm(
            agent: Mock, handlers: Mock
        ) -> None:
            reached = []
            with pytest.raises(SystemExit) as raised:
                async with Botbox(agent):
                    send_sigterm(handlers)
                    await asyncio.sleep(1)
                    reached.append(True)
            assert raised.value.code == 143
            assert isinstance(raised.value.__cause__, asyncio.CancelledError)
            assert reached == []
            task = asyncio.current_task()
            assert task is not None
            assert task.cancelling() == 0

        async def it_exits_143_on_a_sigterm_the_block_swallowed(
            agent: Mock, handlers: Mock
        ) -> None:
            with pytest.raises(SystemExit) as raised:
                async with Botbox(agent):
                    try:
                        send_sigterm(handlers)
                        await asyncio.sleep(1)
                    except asyncio.CancelledError:
                        pass
            assert raised.value.code == 143

        async def it_exits_143_on_a_sigterm_over_another_error(agent: Mock, handlers: Mock) -> None:
            with pytest.raises(SystemExit) as raised:
                async with Botbox(agent):
                    try:
                        send_sigterm(handlers)
                        await asyncio.sleep(1)
                    finally:
                        raise ValueError("teardown failed")
            assert raised.value.code == 143
            assert isinstance(raised.value.__cause__, ValueError)

        async def it_lets_any_other_cancel_through(agent: Mock) -> None:
            async def hold() -> None:
                async with Botbox(agent):
                    await asyncio.sleep(1)

            task = asyncio.ensure_future(hold())
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        async def it_lets_an_error_through_without_a_sigterm(agent: Mock) -> None:
            with pytest.raises(ValueError, match="boom"):
                async with Botbox(agent):
                    raise ValueError("boom")

        async def it_forgets_a_sigterm_once_it_has_exited(agent: Mock, handlers: Mock) -> None:
            box = Botbox(agent)
            with pytest.raises(SystemExit):
                async with box:
                    send_sigterm(handlers)
                    await asyncio.sleep(1)
            handlers.add.reset_mock()
            async with box:
                pass

        async def it_cancels_once_however_many_sigterms_arrive(agent: Mock, handlers: Mock) -> None:
            with pytest.raises(SystemExit) as raised:
                async with Botbox(agent):
                    try:
                        send_sigterm(handlers)
                        await asyncio.sleep(1)
                    finally:
                        send_sigterm(handlers)
                        await asyncio.sleep(0)
            assert raised.value.code == 143
            task = asyncio.current_task()
            assert task is not None
            assert task.cancelling() == 0

        async def it_ignores_a_sigterm_queued_before_it_exited(agent: Mock, handlers: Mock) -> None:
            box = Botbox(agent)
            async with box:
                pass
            send_sigterm(handlers)
            await asyncio.sleep(0)
            handlers.add.reset_mock()
            async with box:
                await asyncio.sleep(0)

        async def it_ignores_a_stale_sigterm_inside_a_later_block(
            agent: Mock, handlers: Mock
        ) -> None:
            box = Botbox(agent)
            async with box:
                pass
            [(_, stale, *args)] = [c.args for c in handlers.add.call_args_list]
            async with box:
                stale(*args)
                await asyncio.sleep(0)

        async def it_leaves_a_programs_own_handler_alone(
            agent: Mock, signals: MagicMock, handlers: Mock
        ) -> None:
            signals.getsignal.return_value = Mock()
            async with Botbox(agent):
                pass
            signals.getsignal.assert_called_once_with(signals.SIGTERM)
            handlers.add.assert_not_called()
            handlers.remove.assert_not_called()

        async def it_restores_only_what_it_installed(
            agent: Mock, signals: MagicMock, handlers: Mock
        ) -> None:
            box = Botbox(agent)
            async with box:
                pass
            signals.getsignal.return_value = Mock()
            handlers.remove.reset_mock()
            async with box:
                pass
            handlers.remove.assert_not_called()

        async def it_does_nothing_off_the_main_thread(
            agent: Mock, threads: MagicMock, handlers: Mock
        ) -> None:
            threads.current_thread.return_value = Mock()
            async with Botbox(agent):
                pass
            handlers.add.assert_not_called()
            handlers.remove.assert_not_called()


def describe_build() -> None:
    async def it_plans_the_build_from_the_agent_and_dockerfile(
        agent: Mock, layer: Path, build_steps: Mock
    ) -> None:
        await Botbox(agent, dockerfile=layer).build()
        build_steps.assert_called_once_with(agent, layer)

    async def it_returns_the_last_steps_tag(agent: Mock) -> None:
        assert await Botbox(agent).build() == "an-agent-123:latest"

    async def it_returns_the_only_steps_tag(agent: Mock, build_steps: Mock) -> None:
        build_steps.return_value = [AGENT_STEP]
        assert await Botbox(agent).build() == "an-agent:latest"

    async def it_builds_each_step_with_the_docker_sdk(agent: Mock, docker_build: Mock) -> None:
        await Botbox(agent).build()
        assert docker_build.call_args_list == [
            call(
                Path("/agents"),
                tag="an-agent:latest",
                file=Path("/agents/D"),
                contexts={"botbox": "/r"},
            ),
            call(
                Path("/consumer"),
                tag="an-agent-123:latest",
                file=Path("/consumer/D"),
                contexts={},
            ),
        ]

    async def it_holds_each_tags_lock_only_while_building_it(agent: Mock, steps: list[str]) -> None:
        await Botbox(agent).build()
        assert steps == [
            "lock an-agent:latest",
            "build an-agent:latest",
            "unlock an-agent:latest",
            "lock an-agent-123:latest",
            "build an-agent-123:latest",
            "unlock an-agent-123:latest",
        ]

    async def it_stops_at_the_first_failed_step(
        agent: Mock, docker_build: Mock, steps: list[str]
    ) -> None:
        docker_build.side_effect = RuntimeError("agent failed")
        with pytest.raises(RuntimeError, match="agent failed"):
            await Botbox(agent).build()
        assert steps == ["lock an-agent:latest", "unlock an-agent:latest"]

    async def it_lets_a_failed_build_through(agent: Mock, docker_build: Mock) -> None:
        failed = CommandFailed()
        docker_build.side_effect = failed
        with pytest.raises(CommandFailed) as raised:
            await Botbox(agent).build()
        assert raised.value is failed

    async def it_releases_the_lock_when_a_build_fails(
        agent: Mock, docker_build: Mock, steps: list[str]
    ) -> None:
        docker_build.side_effect = CommandFailed()
        with pytest.raises(CommandFailed):
            await Botbox(agent).build()
        assert steps == ["lock an-agent:latest", "unlock an-agent:latest"]

    async def it_releases_the_lock_when_a_build_is_cancelled(
        agent: Mock, docker_build: Mock, steps: list[str]
    ) -> None:
        started = asyncio.Event()

        async def hang(*_args: object, **_options: object) -> None:
            started.set()
            await asyncio.Event().wait()

        docker_build.side_effect = hang
        build = asyncio.create_task(Botbox(agent).build())
        await started.wait()
        build.cancel()
        with pytest.raises(asyncio.CancelledError):
            await build
        assert steps == ["lock an-agent:latest", "unlock an-agent:latest"]


TOKEN = "0123456789ab"
AGENT = "botbox-agent-0123456789ab"
PROXY = "botbox-proxy-0123456789ab"


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    scratch = tmp_path / TOKEN
    scratch.mkdir()
    return scratch


@pytest.fixture
def open_umask() -> Iterator[None]:
    previous = os.umask(0)
    try:
        yield
    finally:
        os.umask(previous)


@pytest.fixture
def runner() -> Mock:
    """An agent that runs: its home, credentials, hosts and transcripts."""
    agent = Mock(image="an-agent:latest", home="/home/user", allow=("api.anthropic.com",))
    agent.transcripts = ".claude/**/*.jsonl"
    agent.stage_auth.side_effect = lambda home: (home / ".credentials").write_text("token")
    return agent


@pytest.fixture(autouse=True)
def uuid4() -> Iterator[Mock]:
    with patch("botbox.Botbox.uuid4", autospec=True) as m:
        m.return_value.hex = TOKEN + "cdef0123456789abcdef"
        yield m


@pytest.fixture(autouse=True)
def claim(scratch: Path, steps: list[str]) -> Iterator[Mock]:
    with patch("botbox.Botbox.Claim", autospec=True) as m:
        m.return_value.path = scratch
        m.return_value.cleanup.side_effect = lambda: steps.append("remove temp home")
        yield m


@pytest.fixture(autouse=True)
def reap(steps: list[str]) -> Iterator[Mock]:
    async def reap() -> list[str]:
        steps.append("reap")
        return []

    with patch("botbox.Botbox.reap", autospec=True, side_effect=reap) as m:
        yield m


@pytest.fixture(autouse=True)
def bind_mounts() -> Iterator[Mock]:
    with patch("botbox.Botbox.bind_mounts", autospec=True) as m:
        m.return_value = [("/src", "/home/user/src", "ro")]
        yield m


@pytest.fixture
def jail(scratch: Path) -> Mock:
    return Mock(
        proxy=PROXY,
        sockets=scratch / "sockets",
        envs={"HTTPS_PROXY": "http://127.0.0.1:41893"},
        log="",
    )


@pytest.fixture(autouse=True)
def lockdown(jail: Mock, steps: list[str]) -> Iterator[Mock]:
    @asynccontextmanager
    async def lockdown(*_args: object) -> AsyncIterator[Mock]:
        steps.append("start proxy")
        try:
            yield jail
        finally:
            steps.append("stop proxy")
            jail.log = "CONNECT api.anthropic.com:443\n"

    with patch("botbox.Botbox.lockdown", autospec=True, side_effect=lockdown) as m:
        yield m


@pytest.fixture(autouse=True)
def docker_run(steps: list[str]) -> Iterator[Mock]:
    async def attached(
        _args: list[str],
        *,
        stdout: bytearray,
        stderr: bytearray,
        limits: tuple[int | None, int | None] = (None, None),
        **_options: Any,
    ) -> int:
        steps.append("run agent")
        for into, data, limit in (
            (stdout, b"out\xff\n", limits[0]),
            (stderr, b"err\n", limits[1]),
        ):
            into.extend(data)
            if limit is not None:
                del into[: max(len(into) - limit, 0)]
        return 3

    with patch("botbox.Botbox.docker_run", autospec=True, side_effect=attached) as m:
        yield m


@pytest.fixture(autouse=True)
def agent_exit(steps: list[str]) -> Iterator[Mock]:
    async def exited(*_args: object) -> int:
        steps.append("read exit code")
        return 3

    with patch("botbox.Botbox.agent_exit", autospec=True, side_effect=exited) as m:
        yield m


@pytest.fixture(autouse=True)
def remove(steps: list[str]) -> Iterator[Mock]:
    def removal(name: str) -> str:
        steps.append(f"remove {name}")
        return f"removal of {name}"

    with patch("botbox.Botbox.remove_within", Mock(side_effect=removal)) as m:
        yield m


@pytest.fixture(autouse=True)
def warned(steps: list[str]) -> Iterator[Mock]:
    async def step(removal: Any, what: str) -> None:
        if not isinstance(removal, str):
            await removal
        steps.append(f"warned: {what}")

    with patch("botbox.Botbox.warned", Mock(side_effect=step)) as m:
        yield m


@pytest.fixture(autouse=True)
def settle(steps: list[str]) -> Iterator[Mock]:
    async def settled(step: Any) -> None:
        steps.append("settle")
        await step

    with patch("botbox.Botbox.settle", autospec=True, side_effect=settled) as m:
        yield m


@pytest.fixture(autouse=True)
def read_transcript(steps: list[str]) -> Iterator[Mock]:
    def read(*_args: object) -> dict[str, str]:
        steps.append("read transcript")
        return {".claude/projects/a.jsonl": "{}\n"}

    with patch("botbox.Botbox.read_transcript", autospec=True, side_effect=read) as m:
        yield m


RUN = argparse.ArgumentParser()
for flag in ("--name", "--label", "--workdir", "--network", "--pid", "--user"):
    RUN.add_argument(flag)
for flag in ("--env", "--volume", "--cap-drop", "--security-opt"):
    RUN.add_argument(flag, action="append", default=[])
RUN.add_argument("image")


def agent_options(docker_run: Mock) -> dict[str, Any]:
    """The options of the agent's `docker run`; an unexpected flag fails the parse."""
    [args] = docker_run.call_args.args
    image = args.index("an-agent-123:latest")
    return {**vars(RUN.parse_args(args[: image + 1])), "command": args[image + 1 :]}


def run_steps(steps: list[str]) -> list[str]:
    """The steps from the proxy's start on, past the image build."""
    return steps[steps.index("start proxy") :]


def describe_run() -> None:
    async def it_returns_what_the_run_left(runner: Mock) -> None:
        result = await Botbox(runner).run("claude -p hi")
        assert result.stdout == "out�\n"
        assert result.stderr == "err\n"
        assert result.exit_code == 3
        assert result.transcript == {".claude/projects/a.jsonl": "{}\n"}
        assert result.proxy == "CONNECT api.anthropic.com:443\n"
        assert result.image == "an-agent-123:latest"

    async def it_takes_its_options_by_keyword_only(runner: Mock) -> None:
        with pytest.raises(TypeError):
            await Botbox(runner).run("true", ())  # type: ignore[call-arg]

    def describe_output_caps() -> None:
        async def it_is_not_truncated_under_the_caps(runner: Mock) -> None:
            result = await Botbox(runner, stdout_limit=6, stderr_limit=5).run("true")
            assert (result.stdout, result.stderr) == ("out\ufffd\n", "err\n")
            assert result.truncated is False

        async def it_is_not_truncated_at_the_caps(runner: Mock) -> None:
            result = await Botbox(runner, stdout_limit=5, stderr_limit=4).run("true")
            assert (result.stdout, result.stderr) == ("out\ufffd\n", "err\n")
            assert result.truncated is False

        async def it_keeps_the_end_of_stdout_over_its_cap(runner: Mock) -> None:
            result = await Botbox(runner, stdout_limit=2).run("true")
            assert (result.stdout, result.stderr) == ("\ufffd\n", "err\n")
            assert result.truncated is True

        async def it_keeps_the_end_of_stderr_over_its_cap(runner: Mock) -> None:
            result = await Botbox(runner, stderr_limit=2).run("true")
            assert (result.stdout, result.stderr) == ("out\ufffd\n", "r\n")
            assert result.truncated is True

        async def it_keeps_nothing_with_a_cap_of_0(runner: Mock) -> None:
            result = await Botbox(runner, stdout_limit=0, stderr_limit=0).run("true")
            assert (result.stdout, result.stderr) == ("", "")
            assert result.truncated is True

        async def it_holds_one_byte_past_each_cap_to_see_a_trim(
            runner: Mock, docker_run: Mock
        ) -> None:
            await Botbox(runner, stdout_limit=5, stderr_limit=1).run("true")
            assert docker_run.call_args.kwargs["limits"] == (6, 2)

        async def it_reads_the_exit_code_with_the_kept_stderr(
            runner: Mock, agent_exit: Mock
        ) -> None:
            await Botbox(runner, stderr_limit=2).run("true")
            assert agent_exit.call_args.args[3] == "r\n"

    async def it_checks_the_mounts_before_building(
        runner: Mock, bind_mounts: Mock, docker_build: Mock
    ) -> None:
        bind_mounts.side_effect = ValueError("no such path")
        with pytest.raises(ValueError, match="no such path"):
            await Botbox(runner).run("true", mounts=[("/nope", "/x", "ro")], workdir="/x")
        bind_mounts.assert_called_once_with(
            [("/nope", "/x", "ro")], workdir="/x", home="/home/user"
        )
        docker_build.assert_not_called()

    async def it_claims_a_temp_home_named_after_the_run_token(runner: Mock, claim: Mock) -> None:
        await Botbox(runner).run("true")
        claim.assert_called_once_with(TOKEN)

    async def it_reaps_dead_runs_after_checking_the_mounts_and_before_building(
        runner: Mock, bind_mounts: Mock, steps: list[str]
    ) -> None:
        await Botbox(runner).run("true")
        assert steps[0] == "reap"
        bind_mounts.side_effect = ValueError("no such path")
        steps.clear()
        with pytest.raises(ValueError, match="no such path"):
            await Botbox(runner).run("true")
        assert steps == []

    async def it_stages_the_credentials_into_a_fresh_home(runner: Mock, scratch: Path) -> None:
        await Botbox(runner).run("true")
        runner.stage_auth.assert_called_once_with(scratch / "home")
        assert (scratch / "home" / ".credentials").read_text() == "token"

    @pytest.mark.usefixtures("open_umask")
    async def it_keeps_the_home_to_its_owner_whatever_the_umask(
        runner: Mock, scratch: Path
    ) -> None:
        await Botbox(runner).run("true")
        assert (scratch / "home").stat().st_mode & 0o777 == 0o700

    async def it_locks_down_with_the_agents_hosts_and_the_boxs(
        runner: Mock, lockdown: Mock, scratch: Path
    ) -> None:
        await Botbox(runner, allow=["registry.npmjs.org"]).run("true")
        lockdown.assert_called_once_with(
            ("api.anthropic.com", "registry.npmjs.org"), scratch, TOKEN
        )

    async def it_runs_and_tears_down_in_order(runner: Mock, steps: list[str]) -> None:
        await Botbox(runner).run("true")
        assert run_steps(steps) == [
            "start proxy",
            "run agent",
            "read exit code",
            f"remove {AGENT}",
            "settle",
            f"warned: remove its agent container {AGENT}",
            "read transcript",
            "stop proxy",
            "settle",
            "remove temp home",
            "warned: remove its temp home",
        ]

    async def it_reads_the_transcript_from_the_home(
        runner: Mock, read_transcript: Mock, scratch: Path
    ) -> None:
        await Botbox(runner).run("true")
        read_transcript.assert_called_once_with(scratch / "home", ".claude/**/*.jsonl")

    async def it_reads_the_exit_code_with_the_command_client_and_stderr(
        runner: Mock, docker_run: Mock, agent_exit: Mock
    ) -> None:
        await Botbox(runner).run("true")
        [args] = docker_run.call_args.args
        agent_exit.assert_awaited_once_with(AGENT, ["docker", "run", *args], 3, "err\n")

    def describe_the_agent_container() -> None:
        async def it_runs_the_command_through_the_relay_in_the_image(
            runner: Mock, docker_run: Mock
        ) -> None:
            await Botbox(runner).run("claude -p hi")
            options = agent_options(docker_run)
            assert options["image"] == "an-agent-123:latest"
            assert options["command"] == ["/usr/local/bin/botbox-relay", "sh", "-c", "claude -p hi"]

        async def it_is_named_and_labelled_with_the_run_token(
            runner: Mock, docker_run: Mock
        ) -> None:
            await Botbox(runner).run("true")
            options = agent_options(docker_run)
            assert options["name"] == AGENT
            assert options["label"] == f"botbox.run={TOKEN}"

        async def it_does_not_remove_itself(runner: Mock, docker_run: Mock) -> None:
            await Botbox(runner).run("true")
            [args] = docker_run.call_args.args
            assert "--rm" not in args

        async def it_reads_nothing_and_keeps_its_output(runner: Mock, docker_run: Mock) -> None:
            await Botbox(runner).run("true")
            options = docker_run.call_args.kwargs
            assert options["stdin"] == asyncio.subprocess.DEVNULL
            assert options["stdout"] is not options["stderr"]

        async def it_joins_the_proxy_with_no_network_as_the_unprivileged_user(
            runner: Mock, docker_run: Mock
        ) -> None:
            await Botbox(runner).run("true")
            options = agent_options(docker_run)
            assert options["network"] == "none"
            assert options["pid"] == f"container:{PROXY}"
            assert options["user"] == "user"
            assert options["cap_drop"] == ["ALL"]
            assert options["security_opt"] == ["no-new-privileges"]
            assert options["env"] == ["HTTPS_PROXY=http://127.0.0.1:41893"]

        async def it_mounts_the_home_the_sockets_and_the_callers_mounts(
            runner: Mock, docker_run: Mock, scratch: Path
        ) -> None:
            await Botbox(runner).run("true")
            assert agent_options(docker_run)["volume"] == [
                f"{scratch / 'home'}:/home/user:rw",
                f"{scratch / 'sockets'}:/run/botbox:ro",
                "/src:/home/user/src:ro",
            ]

        async def it_works_in_the_home_by_default(runner: Mock, docker_run: Mock) -> None:
            await Botbox(runner).run("true")
            assert agent_options(docker_run)["workdir"] == "/home/user"

        async def it_works_in_the_workdir_it_is_given(runner: Mock, docker_run: Mock) -> None:
            await Botbox(runner).run("true", workdir=Path("/home/user/src"))
            assert agent_options(docker_run)["workdir"] == "/home/user/src"

    def describe_failure() -> None:
        async def it_lets_a_failed_docker_command_through_after_tearing_down(
            runner: Mock, agent_exit: Mock, steps: list[str]
        ) -> None:
            failed = CommandFailed()
            agent_exit.side_effect = failed
            with pytest.raises(CommandFailed) as raised:
                await Botbox(runner).run("true")
            assert raised.value is failed
            assert f"remove {AGENT}" in steps
            assert steps[-1] == "warned: remove its temp home"

        async def it_lets_other_errors_through_after_tearing_down(
            runner: Mock, docker_run: Mock, steps: list[str]
        ) -> None:
            docker_run.side_effect = FileNotFoundError("docker")
            with pytest.raises(FileNotFoundError):
                await Botbox(runner).run("true")
            assert run_steps(steps) == [
                "start proxy",
                f"remove {AGENT}",
                "settle",
                f"warned: remove its agent container {AGENT}",
                "stop proxy",
                "settle",
                "remove temp home",
                "warned: remove its temp home",
            ]

        async def it_removes_the_temp_home_when_staging_fails(
            runner: Mock, lockdown: Mock, steps: list[str]
        ) -> None:
            runner.stage_auth.side_effect = PermissionError("no credentials")
            with pytest.raises(PermissionError):
                await Botbox(runner).run("true")
            lockdown.assert_not_called()
            assert steps[-1] == "warned: remove its temp home"

        async def it_tears_down_when_cancelled_mid_run(
            runner: Mock, docker_run: Mock, steps: list[str]
        ) -> None:
            started = asyncio.Event()

            async def hang(*_args: object, **_options: object) -> int:
                started.set()
                await asyncio.Event().wait()
                return 0

            docker_run.side_effect = hang
            task = asyncio.create_task(Botbox(runner).run("sleep 600"))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert run_steps(steps) == [
                "start proxy",
                f"remove {AGENT}",
                "settle",
                f"warned: remove its agent container {AGENT}",
                "stop proxy",
                "settle",
                "remove temp home",
                "warned: remove its temp home",
            ]


@pytest.fixture
def held(steps: list[str]) -> Mock:
    """The live session `hold_session` yields: its CLI printed, then exits 3 once input ends."""
    live = Mock(stdout=Mock(into=bytearray(b"out\xff\n")), stderr=bytearray(b"err\n"), result=None)

    def end_input() -> None:
        steps.append("end input")
        live.client.set_result(3)

    live.stdin.close.side_effect = end_input
    return live


@pytest.fixture(autouse=True)
def hold_session(held: Mock, steps: list[str]) -> Iterator[Mock]:
    @asynccontextmanager
    async def hold(*_args: object) -> AsyncIterator[Mock]:
        held.agent = _args[0]
        held.client = asyncio.get_running_loop().create_future()
        steps.append("hold session")
        try:
            yield held
        finally:
            steps.append("release session")

    with patch("botbox.Botbox.hold_session", autospec=True, side_effect=hold) as m:
        yield m


def session_args(hold_session: Mock) -> list[str]:
    [_agent, args] = hold_session.call_args.args
    return list(args)


def session_options(hold_session: Mock) -> dict[str, Any]:
    args = session_args(hold_session)
    assert args[0] == "--interactive"
    image = args.index("an-agent-123:latest")
    return {**vars(RUN.parse_args(args[1 : image + 1])), "command": args[image + 1 :]}


def describe_session() -> None:
    @pytest.fixture(autouse=True)
    def session_reader(read_transcript: Mock) -> Iterator[None]:
        with patch("botbox.session_result.read_transcript", read_transcript):
            yield

    @pytest.fixture
    def talker(runner: Mock) -> Mock:
        # Set outright: the SessionAgent check looks attributes up statically, past Mock's magic.
        for method in ("stage_auth", "command", "session_command", "encode", "turn_ended"):
            setattr(runner, method, getattr(runner, method))
        runner.dockerfile = Path("/agents/D")
        runner.session_command.return_value = "an-agent --stream"
        return runner

    async def it_yields_the_held_session_and_leaves_its_result(talker: Mock, held: Mock) -> None:
        async with Botbox(talker).session() as live:
            assert live is held
            assert live.result is None
        result = live.result
        assert result is not None
        assert result.stdout == "out�\n"
        assert result.stderr == "err\n"
        assert result.exit_code == 3
        assert result.transcript == {".claude/projects/a.jsonl": "{}\n"}
        assert result.proxy == "CONNECT api.anthropic.com:443\n"
        assert result.image == "an-agent-123:latest"

    async def it_refuses_an_agent_with_no_session_mode(runner: Mock, docker_build: Mock) -> None:
        with pytest.raises(TypeError, match=r"^Mock has no session mode$"):
            async with Botbox(runner).session():
                pass
        docker_build.assert_not_called()

    async def it_lets_an_agent_refuse_a_session_before_building(
        talker: Mock, docker_build: Mock
    ) -> None:
        talker.session_command.side_effect = NotImplementedError("no session mode")
        with pytest.raises(NotImplementedError):
            async with Botbox(talker).session():
                pass
        docker_build.assert_not_called()

    async def it_takes_its_options_by_keyword_only(talker: Mock) -> None:
        with pytest.raises(TypeError):
            async with Botbox(talker).session(()):  # type: ignore[call-arg]
                pass

    @pytest.mark.usefixtures("open_umask")
    async def it_keeps_the_home_to_its_owner_whatever_the_umask(
        talker: Mock, scratch: Path
    ) -> None:
        async with Botbox(talker).session():
            pass
        assert (scratch / "home").stat().st_mode & 0o777 == 0o700

    async def it_checks_the_mounts_before_building(
        talker: Mock, bind_mounts: Mock, docker_build: Mock
    ) -> None:
        bind_mounts.side_effect = ValueError("no such path")
        with pytest.raises(ValueError, match="no such path"):
            async with Botbox(talker).session(mounts=[("/nope", "/x", "ro")], workdir="/x"):
                pass
        bind_mounts.assert_called_once_with(
            [("/nope", "/x", "ro")], workdir="/x", home="/home/user"
        )
        docker_build.assert_not_called()

    async def it_stages_a_home_named_after_the_run_token_and_locks_it_down(
        talker: Mock, claim: Mock, lockdown: Mock, scratch: Path, steps: list[str]
    ) -> None:
        async with Botbox(talker, allow=["registry.npmjs.org"]).session():
            pass
        assert steps[0] == "reap"
        claim.assert_called_once_with(TOKEN)
        assert (scratch / "home" / ".credentials").read_text() == "token"
        lockdown.assert_called_once_with(
            ("api.anthropic.com", "registry.npmjs.org"), scratch, TOKEN
        )

    async def it_holds_the_session_then_tears_down_in_order(talker: Mock, steps: list[str]) -> None:
        async with Botbox(talker).session():
            steps.append("talk")
        assert run_steps(steps) == [
            "start proxy",
            "hold session",
            "talk",
            "end input",
            "release session",
            "read exit code",
            f"remove {AGENT}",
            "settle",
            f"warned: remove its agent container {AGENT}",
            "stop proxy",
            "settle",
            "read transcript",
            "warned: read its session artifacts",
            "settle",
            "remove temp home",
            "warned: remove its temp home",
        ]

    async def it_reads_the_exit_code_with_the_command_client_and_stderr(
        talker: Mock, hold_session: Mock, agent_exit: Mock
    ) -> None:
        async with Botbox(talker).session():
            pass
        args = session_args(hold_session)
        agent_exit.assert_awaited_once_with(AGENT, ["docker", "run", *args], 3, "err\n")
        assert hold_session.call_args.args[0] is talker

    async def it_reads_the_transcript_from_the_home(
        talker: Mock, read_transcript: Mock, scratch: Path
    ) -> None:
        async with Botbox(talker).session():
            pass
        read_transcript.assert_called_once_with(scratch / "home", ".claude/**/*.jsonl")

    def describe_the_agent_container() -> None:
        async def it_runs_the_session_command_attached_through_the_relay(
            talker: Mock, hold_session: Mock
        ) -> None:
            async with Botbox(talker).session():
                pass
            options = session_options(hold_session)
            assert options["image"] == "an-agent-123:latest"
            assert options["command"] == [
                "/usr/local/bin/botbox-relay",
                "sh",
                "-c",
                "an-agent --stream",
            ]

        async def it_is_named_and_labelled_with_the_run_token_and_not_removed_on_exit(
            talker: Mock, hold_session: Mock
        ) -> None:
            async with Botbox(talker).session():
                pass
            options = session_options(hold_session)
            assert options["name"] == AGENT
            assert options["label"] == f"botbox.run={TOKEN}"
            assert "--rm" not in session_args(hold_session)

        async def it_is_locked_down_like_a_run(
            talker: Mock, hold_session: Mock, scratch: Path
        ) -> None:
            async with Botbox(talker).session(workdir="/home/user/src"):
                pass
            options = session_options(hold_session)
            assert options["network"] == "none"
            assert options["pid"] == f"container:{PROXY}"
            assert options["user"] == "user"
            assert options["cap_drop"] == ["ALL"]
            assert options["security_opt"] == ["no-new-privileges"]
            assert options["env"] == ["HTTPS_PROXY=http://127.0.0.1:41893"]
            assert options["workdir"] == "/home/user/src"
            assert options["volume"] == [
                f"{scratch / 'home'}:/home/user:rw",
                f"{scratch / 'sockets'}:/run/botbox:ro",
                "/src:/home/user/src:ro",
            ]

    def describe_failure() -> None:
        async def it_lets_a_failed_docker_command_through_after_tearing_down(
            talker: Mock, agent_exit: Mock, held: Mock, steps: list[str]
        ) -> None:
            failed = CommandFailed()
            agent_exit.side_effect = failed
            with pytest.raises(CommandFailed) as raised:
                async with Botbox(talker).session():
                    pass
            assert raised.value is failed
            assert f"remove {AGENT}" in steps
            assert steps[-1] == "warned: remove its temp home"
            assert held.result is not None
            assert held.result.exit_code == -1
            assert held.result.transcript == {".claude/projects/a.jsonl": "{}\n"}
            assert held.result.proxy == "CONNECT api.anthropic.com:443\n"

        async def it_tears_down_without_ending_input_when_the_block_fails(
            talker: Mock, held: Mock, steps: list[str]
        ) -> None:
            with pytest.raises(ValueError, match="boom"):
                async with Botbox(talker).session():
                    raise ValueError("boom")
            assert run_steps(steps) == [
                "start proxy",
                "hold session",
                "release session",
                f"remove {AGENT}",
                "settle",
                f"warned: remove its agent container {AGENT}",
                "stop proxy",
                "settle",
                "read transcript",
                "warned: read its session artifacts",
                "settle",
                "remove temp home",
                "warned: remove its temp home",
            ]
            assert held.result is not None
            assert held.result.exit_code == -1
            assert held.result.transcript == {".claude/projects/a.jsonl": "{}\n"}
            assert held.result.proxy == "CONNECT api.anthropic.com:443\n"

        async def it_tears_down_when_cancelled_mid_turn(
            talker: Mock, held: Mock, steps: list[str]
        ) -> None:
            talking = asyncio.Event()

            async def talk() -> None:
                async with Botbox(talker).session():
                    talking.set()
                    await asyncio.Event().wait()

            task = asyncio.create_task(talk())
            await talking.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert run_steps(steps) == [
                "start proxy",
                "hold session",
                "release session",
                f"remove {AGENT}",
                "settle",
                f"warned: remove its agent container {AGENT}",
                "stop proxy",
                "settle",
                "read transcript",
                "warned: read its session artifacts",
                "settle",
                "remove temp home",
                "warned: remove its temp home",
            ]
            assert held.result is not None
            assert held.result.exit_code == -1
            assert held.result.transcript == {".claude/projects/a.jsonl": "{}\n"}
            assert held.result.proxy == "CONNECT api.anthropic.com:443\n"

        async def it_raises_a_client_that_failed_to_start(
            talker: Mock, held: Mock, steps: list[str]
        ) -> None:
            held.stdin.close.side_effect = lambda: held.client.set_exception(
                FileNotFoundError("docker")
            )
            with pytest.raises(FileNotFoundError):
                async with Botbox(talker).session():
                    pass
            assert f"remove {AGENT}" in steps
            assert steps[-1] == "warned: remove its temp home"

        async def it_removes_no_container_when_the_lockdown_fails(
            talker: Mock, lockdown: Mock, hold_session: Mock, steps: list[str]
        ) -> None:
            lockdown.side_effect = RuntimeError("proxy never came up")
            with pytest.raises(RuntimeError, match="proxy never came up"):
                async with Botbox(talker).session():
                    pass
            hold_session.assert_not_called()
            assert not [step for step in steps if step.startswith("remove botbox-agent")]
            assert steps[-1] == "warned: remove its temp home"

        async def it_removes_the_temp_home_when_staging_fails(
            talker: Mock, lockdown: Mock, steps: list[str]
        ) -> None:
            talker.stage_auth.side_effect = PermissionError("no credentials")
            with pytest.raises(PermissionError):
                async with Botbox(talker).session():
                    pass
            lockdown.assert_not_called()
            assert steps[-1] == "warned: remove its temp home"
