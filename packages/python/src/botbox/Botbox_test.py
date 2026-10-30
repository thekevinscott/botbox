import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest

from botbox.Botbox import Botbox

LABEL_VALUE = "/tmp/runs/2026-10-27T14:38:00-ab12"


@dataclass(frozen=True)
class FakeMount:
    kind: str
    source: str
    target: str
    read_only: bool = False


@pytest.fixture(autouse=True)
def no_env_labels() -> Iterator[None]:
    with patch.dict(os.environ):
        os.environ.pop("BOTBOX_LABELS", None)
        yield


@pytest.fixture(autouse=True)
def fake_mount() -> Iterator[None]:
    with patch("botbox.Botbox.DockerMount", FakeMount):
        yield


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
    """Each build, in order."""
    return []


@pytest.fixture(autouse=True)
def build_steps() -> Iterator[Mock]:
    with patch("botbox.Botbox.build_steps", autospec=True) as m:
        m.return_value = [AGENT_STEP, LAYER_STEP]
        yield m


@pytest.fixture(autouse=True)
def dockerfile(steps: list[str]) -> Iterator[Mock]:
    async def build(tag: str, **_options: Any) -> None:
        steps.append(f"build {tag}")

    with patch("botbox.Botbox.Dockerfile", autospec=True) as m:
        m.return_value.build.side_effect = build
        yield m


@pytest.fixture
def docker_build(dockerfile: Mock) -> Mock:
    build: Mock = dockerfile.return_value.build
    return build


class CommandFailed(Exception):
    """Stands in for the SDK's `DockerException`."""


class Timeout(Exception):
    """Stands in for `botbox.Timeout`."""

    def __init__(self, seconds: float, result: Any) -> None:
        self.seconds = seconds
        self.result = result


@pytest.fixture(autouse=True)
def timeout_error() -> Iterator[None]:
    with patch("botbox.Botbox.Timeout", Timeout):
        yield


def send_sigterm(handlers: Mock) -> None:
    """Call the SIGTERM handler the box added to the loop."""
    [(_, handler, *args)] = [c.args for c in handlers.add.call_args_list]
    handler(*args)


def describe_botbox() -> None:
    def it_keeps_the_agent(agent: Mock) -> None:
        assert Botbox(agent).agent is agent

    def it_leaves_memory_uncapped_by_default(agent: Mock) -> None:
        assert Botbox(agent).memory is None

    def it_defaults_to_4096_pids(agent: Mock) -> None:
        assert Botbox(agent).pids == 4096

    def it_accepts_one_pid(agent: Mock) -> None:
        assert Botbox(agent, pids=1).pids == 1

    @pytest.mark.parametrize("pids", [0, -1])
    def it_rejects_nonpositive_pids(agent: Mock, pids: int) -> None:
        with pytest.raises(ValueError, match="pids must be at least 1"):
            Botbox(agent, pids=pids)

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

    def it_refuses_to_run_an_agent_as_root(agent: Mock, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(os, "getuid", lambda: 0)
        with pytest.raises(RuntimeError, match="root"):
            Botbox(agent)

    def it_has_no_timeout_by_default(agent: Mock) -> None:
        assert Botbox(agent).timeout is None

    def it_holds_the_timeout(agent: Mock) -> None:
        assert Botbox(agent, timeout=30).timeout == 30

    def it_copies_caller_labels(agent: Mock) -> None:
        labels = {"test.run": LABEL_VALUE}
        box = Botbox(agent, labels=labels)
        labels["test.run"] = "two"
        assert box.labels == {"test.run": LABEL_VALUE}

    def it_reserves_the_cleanup_label(agent: Mock) -> None:
        with pytest.raises(ValueError, match=r"botbox\.run"):
            Botbox(agent, labels={"botbox.run": "other"})

    @pytest.mark.parametrize("seconds", [0, -1])
    def it_refuses_a_timeout_that_is_not_positive(agent: Mock, seconds: float) -> None:
        with pytest.raises(ValueError, match="timeout"):
            Botbox(agent, timeout=seconds)

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

    async def it_builds_each_steps_dockerfile_in_its_context(
        agent: Mock, dockerfile: Mock, docker_build: Mock
    ) -> None:
        await Botbox(agent).build()
        assert dockerfile.call_args_list == [
            call(Path("/agents/D"), context=Path("/agents")),
            call(Path("/consumer/D"), context=Path("/consumer")),
        ]
        assert docker_build.call_args_list == [
            call("an-agent:latest", contexts={"botbox": "/r"}),
            call("an-agent-123:latest", contexts={}),
        ]

    async def it_builds_each_step_in_order(agent: Mock, steps: list[str]) -> None:
        await Botbox(agent).build()
        assert steps == ["build an-agent:latest", "build an-agent-123:latest"]

    async def it_stops_at_the_first_failed_step(agent: Mock, docker_build: Mock) -> None:
        docker_build.side_effect = RuntimeError("agent failed")
        with pytest.raises(RuntimeError, match="agent failed"):
            await Botbox(agent).build()
        assert docker_build.await_count == 1

    async def it_lets_a_failed_build_through(agent: Mock, docker_build: Mock) -> None:
        failed = CommandFailed()
        docker_build.side_effect = failed
        with pytest.raises(CommandFailed) as raised:
            await Botbox(agent).build()
        assert raised.value is failed


TOKEN = "0123456789ab"
AGENT = "botbox-agent-0123456789ab"
PROXY = "botbox-proxy-0123456789ab"


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    scratch = tmp_path / f"botbox-{TOKEN}-x"
    scratch.mkdir()
    return scratch


ARCHIVE = b"the staged home"
SIZE_ENV = "BOTBOX_HOME_BYTES"
ENDED = Mock(name="ended", exit_code=3)


def staged() -> bytes:
    return ARCHIVE


def staged_env() -> dict[str, str]:
    """The env that tells the relay how much of its stdin is the staged archive."""
    return {SIZE_ENV: str(len(ARCHIVE))}


@pytest.fixture(autouse=True)
def home_files() -> Iterator[Mock]:
    with patch("botbox.Botbox.HomeFiles", autospec=True) as m:
        m.return_value.archive.return_value = ARCHIVE
        yield m


@pytest.fixture(autouse=True)
def send_home() -> Iterator[AsyncMock]:
    with patch("botbox.Botbox.send_home", autospec=True) as m:
        yield m


@pytest.fixture
def runner() -> Mock:
    """An agent that runs: its home, credentials, hosts and transcripts."""
    agent = Mock(
        image="an-agent:latest",
        home="/home/user",
        allow=("api.anthropic.com",),
        credential_source=None,
    )
    agent.sessions_dir = ".claude/projects"
    agent.stage_auth.side_effect = lambda home: home.write(".credentials", "token")
    return agent


@pytest.fixture(autouse=True)
def uuid4() -> Iterator[Mock]:
    with patch("botbox.Botbox.uuid4", autospec=True) as m:
        m.return_value.hex = TOKEN + "cdef0123456789abcdef"
        yield m


@pytest.fixture(autouse=True)
def temporary_directory(scratch: Path, steps: list[str]) -> Iterator[Mock]:
    with patch("botbox.Botbox.TemporaryDirectory", autospec=True) as m:
        m.return_value.name = str(scratch)
        m.return_value.cleanup.side_effect = lambda: steps.append("remove temp directory")
        yield m


@pytest.fixture(autouse=True)
def bind_mounts() -> Iterator[Mock]:
    with patch("botbox.Botbox.bind_mounts", autospec=True) as m:
        m.return_value = [("/src", "/home/user/src", "ro")]
        yield m


@pytest.fixture
def jail() -> Mock:
    proxy = Mock()
    proxy.name = PROXY

    def mount(target: str, *, read_only: bool) -> FakeMount:
        return FakeMount("volume", "botbox-run-0123456789ab", target, read_only=read_only)

    return Mock(
        proxy=proxy,
        volume=Mock(mount=mount),
        envs={"HTTPS_PROXY": "http://127.0.0.1:41893"},
        credentials=None,
    )


class Container:
    """A container wrapped by name."""

    def __init__(self, name: str) -> None:
        self.name = name


@pytest.fixture(autouse=True)
def container() -> Iterator[None]:
    with patch("botbox.Botbox.Container", Container):
        yield


@pytest.fixture(autouse=True)
def lockdown(jail: Mock, steps: list[str]) -> Iterator[Mock]:
    @asynccontextmanager
    async def lockdown(*_args: object, **_options: object) -> AsyncIterator[Mock]:
        steps.append("start proxy")
        try:
            yield jail
        finally:
            steps.append("stop proxy")

    with patch("botbox.Botbox.lockdown", autospec=True, side_effect=lockdown) as m:
        yield m


def exited(name: str, code: int) -> Mock:
    """The container `Image.run` returns, its client already exited with `code`."""
    container = Mock(wait=AsyncMock(return_value=code))
    container.name = name
    return container


@pytest.fixture(autouse=True)
def image(steps: list[str]) -> Iterator[Mock]:
    async def attached(*_command: str, name: str, stdout: Any, stderr: Any, **_: Any) -> Mock:
        steps.append("run agent")
        stdout(b"out\xff\n")
        stderr(b"err\n")
        return exited(name, 3)

    with patch("botbox.Botbox.Image", autospec=True) as m:
        m.return_value.run.side_effect = attached
        yield m


@pytest.fixture
def docker_run(image: Mock) -> Mock:
    run: Mock = image.return_value.run
    return run


@pytest.fixture(autouse=True)
def agent_exit(steps: list[str]) -> Iterator[Mock]:
    async def exited(*_args: object) -> Mock:
        steps.append("read exit code")
        return ENDED

    with patch("botbox.Botbox.agent_exit", autospec=True, side_effect=exited) as m:
        yield m


@pytest.fixture(autouse=True)
def remove(steps: list[str]) -> Iterator[Mock]:
    def removal(container: Container) -> str:
        steps.append(f"remove {container.name}")
        return f"removal of {container.name}"

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


def agent_options(docker_run: Mock, image: Mock) -> dict[str, Any]:
    """The agent's `Image.run` options, with its image and command."""
    [tag] = image.call_args.args
    return {**docker_run.call_args.kwargs, "image": tag, "command": list(docker_run.call_args.args)}


def run_steps(steps: list[str]) -> list[str]:
    """The steps from the proxy's start on, past the image build."""
    return steps[steps.index("start proxy") :]


def hang_forever(steps: list[str]) -> Any:
    """A `docker run` that prints part of its output, then never exits."""

    async def hang(*_command: str, stdout: Any, stderr: Any, **_options: Any) -> Mock:
        steps.append("run agent")
        stdout(b"partial\n")
        stderr(b"err\n")
        await asyncio.Event().wait()
        raise AssertionError

    return hang


def stuck_lockdown(*_args: object, **_options: object) -> Any:
    """A proxy that never comes up."""

    @asynccontextmanager
    async def lockdown() -> AsyncIterator[Mock]:
        await asyncio.Event().wait()
        yield Mock()

    return lockdown()


def describe_run() -> None:
    async def it_returns_how_the_agent_container_ended(runner: Mock) -> None:
        assert await Botbox(runner).run("claude -p hi") is ENDED

    async def it_takes_its_options_by_keyword_only(runner: Mock) -> None:
        with pytest.raises(TypeError):
            await Botbox(runner).run("true", ())  # type: ignore[call-arg]

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

    async def it_names_the_temp_home_after_the_run_token(
        runner: Mock, temporary_directory: Mock
    ) -> None:
        await Botbox(runner).run("true")
        temporary_directory.assert_called_once_with(prefix=f"botbox-{TOKEN}-")

    async def it_sends_the_staged_credentials_on_the_agents_stdin_then_closes_it(
        runner: Mock, docker_run: Mock, send_home: AsyncMock, home_files: Mock
    ) -> None:
        await Botbox(runner).run("true")
        runner.stage_auth.assert_called_once_with(home_files.return_value)
        assert docker_run.call_args.kwargs["stdin"] == asyncio.subprocess.PIPE
        stdin = send_home.call_args.args[0]
        send_home.assert_called_once_with(stdin, staged())
        stdin.close.assert_called_once_with()

    async def it_gives_the_agent_no_stdin_with_nothing_staged(
        runner: Mock, docker_run: Mock, send_home: AsyncMock, home_files: Mock
    ) -> None:
        home_files.return_value.archive.return_value = b""
        await Botbox(runner).run("true")
        assert docker_run.call_args.kwargs["stdin"] == asyncio.subprocess.DEVNULL
        assert SIZE_ENV not in docker_run.call_args.kwargs["env"]
        send_home.assert_not_called()

    async def it_makes_no_home_on_the_host(runner: Mock, scratch: Path) -> None:
        await Botbox(runner).run("true")
        assert not (scratch / "home").exists()

    async def it_locks_down_with_the_agents_hosts_and_the_boxs(
        runner: Mock, lockdown: Mock, scratch: Path
    ) -> None:
        await Botbox(runner, allow=["registry.npmjs.org"]).run("true")
        lockdown.assert_called_once_with(
            ("api.anthropic.com", "registry.npmjs.org"),
            scratch,
            TOKEN,
            None,
            credential=None,
            labels={},
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
            "stop proxy",
            "settle",
            "remove temp directory",
            "warned: remove its temp directory",
        ]

    async def it_reads_the_exit_code_with_the_container_client_and_stderr(
        runner: Mock, agent_exit: Mock
    ) -> None:
        await Botbox(runner).run("true")
        [container, client, stderr] = agent_exit.call_args.args
        assert (container.name, client, stderr) == (AGENT, 3, "err\n")

    async def it_gives_only_the_tail_of_a_long_stderr(
        runner: Mock, docker_run: Mock, agent_exit: Mock
    ) -> None:
        async def attached(*_command: str, name: str, stderr: Any, **_: Any) -> Mock:
            stderr(b"x" * 65536 + b"tail")
            return exited(name, 3)

        docker_run.side_effect = attached
        await Botbox(runner).run("true")
        assert agent_exit.call_args.args[2] == "x" * 65532 + "tail"

    async def it_keeps_the_streams_in_the_temp_home(runner: Mock, scratch: Path) -> None:
        await Botbox(runner).run("true")
        assert (scratch / "stdout.txt").read_bytes() == b"out\xff\n"
        assert (scratch / "stderr.txt").read_bytes() == b"err\n"

    def describe_the_agent_container() -> None:
        async def it_passes_default_pids_limit_to_the_agent(runner: Mock, docker_run: Mock) -> None:
            await Botbox(runner).run("true")
            assert docker_run.call_args.kwargs["pids_limit"] == 4096

        @pytest.mark.parametrize("pids", [32, None])
        async def it_passes_the_pids_limit_to_the_agent(
            runner: Mock, docker_run: Mock, pids: int | None
        ) -> None:
            await Botbox(runner, pids=pids).run("true")
            assert docker_run.call_args.kwargs["pids_limit"] == pids

        async def it_caps_only_the_agent_memory(runner: Mock, docker_run: Mock) -> None:
            await Botbox(runner, memory="64m").run("true")
            assert docker_run.call_args.kwargs["memory"] == "64m"

        async def it_runs_the_command_through_the_relay_in_the_image(
            runner: Mock, docker_run: Mock, image: Mock
        ) -> None:
            await Botbox(runner).run("claude -p hi")
            options = agent_options(docker_run, image)
            assert options["image"] == "an-agent-123:latest"
            assert options["command"] == ["/usr/local/bin/botbox-relay", "sh", "-c", "claude -p hi"]

        async def it_is_named_and_labelled_with_the_run_token(
            runner: Mock, docker_run: Mock
        ) -> None:
            await Botbox(runner).run("true")
            options = docker_run.call_args.kwargs
            assert options["name"] == AGENT
            assert options["labels"] == {"botbox.run": TOKEN}

        async def it_merges_caller_labels_into_the_agent_container(
            runner: Mock, docker_run: Mock, lockdown: Mock
        ) -> None:
            await Botbox(runner, labels={"test.run": LABEL_VALUE}).run("true")
            assert docker_run.call_args.kwargs["labels"] == {
                "test.run": LABEL_VALUE,
                "botbox.run": TOKEN,
            }
            assert lockdown.call_args.kwargs["labels"] == {"test.run": LABEL_VALUE}

        async def it_merges_env_labels_under_caller_labels(
            runner: Mock, docker_run: Mock, lockdown: Mock
        ) -> None:
            os.environ["BOTBOX_LABELS"] = f"env.run={LABEL_VALUE}\ntest.run=env"
            await Botbox(runner, labels={"test.run": "caller"}).run("true")
            expected = {"env.run": LABEL_VALUE, "test.run": "caller"}
            assert docker_run.call_args.kwargs["labels"] == {**expected, "botbox.run": TOKEN}
            assert lockdown.call_args.kwargs["labels"] == expected

        async def it_refuses_bad_env_labels_before_building(
            runner: Mock, docker_build: Mock
        ) -> None:
            os.environ["BOTBOX_LABELS"] = "botbox.run=other"
            with pytest.raises(ValueError, match=r"botbox\.run"):
                await Botbox(runner).run("true")
            docker_build.assert_not_called()

        async def it_does_not_remove_itself_and_reads_nothing(
            runner: Mock, docker_run: Mock
        ) -> None:
            await Botbox(runner).run("true")
            options = docker_run.call_args.kwargs
            assert "rm" not in options
            assert options["stdout"] is not options["stderr"]

        @pytest.mark.parametrize(("uid", "gid"), [(1003, 1005), (2456, 3456)])
        async def it_runs_the_agent_as_the_host_user(
            runner: Mock, docker_run: Mock, monkeypatch: pytest.MonkeyPatch, uid: int, gid: int
        ) -> None:
            monkeypatch.setattr(os, "getuid", lambda: uid)
            monkeypatch.setattr(os, "getgid", lambda: gid)
            await Botbox(runner).run("true")
            assert docker_run.call_args.kwargs["user"] == f"{uid}:{gid}"

        async def it_joins_the_proxy_with_no_network_as_the_unprivileged_user(
            runner: Mock, docker_run: Mock
        ) -> None:
            await Botbox(runner).run("true")
            options = docker_run.call_args.kwargs
            assert options["network"] == "none"
            assert options["pid"] == f"container:{PROXY}"
            assert options["user"] == f"{os.getuid()}:{os.getgid()}"
            assert options["cap_drop"] == ["ALL"]
            assert options["security_opt"] == ["no-new-privileges"]
            assert options["log_driver"] == "none"
            assert options["env"] == {
                "HOME": "/home/user",
                **staged_env(),
                "HTTPS_PROXY": "http://127.0.0.1:41893",
            }

        async def it_mounts_the_proxy_volume_and_the_callers_mounts(
            runner: Mock, docker_run: Mock
        ) -> None:
            await Botbox(runner).run("true")
            assert docker_run.call_args.kwargs["mounts"] == [
                FakeMount("volume", "botbox-run-0123456789ab", "/run/botbox", read_only=True),
                FakeMount("bind", "/src", "/home/user/src", read_only=True),
            ]

        async def it_works_in_the_home_by_default(runner: Mock, docker_run: Mock) -> None:
            await Botbox(runner).run("true")
            assert docker_run.call_args.kwargs["workdir"] == "/home/user"

        async def it_works_in_the_workdir_it_is_given(runner: Mock, docker_run: Mock) -> None:
            await Botbox(runner).run("true", workdir=Path("/home/user/src"))
            assert docker_run.call_args.kwargs["workdir"] == "/home/user/src"

    def describe_failure() -> None:
        async def it_lets_a_failed_docker_command_through_after_tearing_down(
            runner: Mock, agent_exit: Mock, steps: list[str], output: Path
        ) -> None:
            failed = CommandFailed()
            agent_exit.side_effect = failed
            with pytest.raises(CommandFailed) as raised:
                await Botbox(runner).run("true", output=output)
            assert raised.value is failed
            assert f"remove {AGENT}" in steps
            assert steps[-1] == "warned: remove its temp directory"

        async def it_lets_other_errors_through_after_tearing_down(
            runner: Mock, docker_run: Mock, steps: list[str], output: Path
        ) -> None:
            docker_run.side_effect = FileNotFoundError("docker")
            with pytest.raises(FileNotFoundError):
                await Botbox(runner).run("true", output=output)
            assert run_steps(steps) == [
                "start proxy",
                f"remove {AGENT}",
                "settle",
                f"warned: remove its agent container {AGENT}",
                "stop proxy",
                "settle",
                "remove temp directory",
                "warned: remove its temp directory",
            ]

        async def it_builds_and_starts_nothing_when_staging_fails(
            runner: Mock, docker_build: Mock, temporary_directory: Mock, output: Path
        ) -> None:
            runner.stage_auth.side_effect = PermissionError("no credentials")
            with pytest.raises(PermissionError):
                await Botbox(runner).run("true", output=output)
            docker_build.assert_not_called()
            temporary_directory.assert_not_called()

        async def it_tears_down_when_cancelled_mid_run(
            runner: Mock, docker_run: Mock, steps: list[str], output: Path
        ) -> None:
            started = asyncio.Event()

            async def hang(*_args: object, stdout: Any, **_options: object) -> Mock:
                stdout(b"partial\n")
                started.set()
                await asyncio.Event().wait()
                raise AssertionError

            docker_run.side_effect = hang
            task = asyncio.create_task(Botbox(runner).run("sleep 600", output=output))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert (output / "stdout.txt").read_bytes() == b"partial\n"
            assert run_steps(steps) == [
                "start proxy",
                f"remove {AGENT}",
                "settle",
                f"warned: remove its agent container {AGENT}",
                "stop proxy",
                "settle",
                "remove temp directory",
                "warned: remove its temp directory",
            ]

    def describe_timeout() -> None:
        async def it_raises_a_timeout_holding_only_the_exit_code_without_output(
            runner: Mock, docker_run: Mock
        ) -> None:
            async def hang(*_args: object, **_options: object) -> Mock:
                await asyncio.Event().wait()
                raise AssertionError

            docker_run.side_effect = hang
            with pytest.raises(Timeout) as raised:
                await Botbox(runner, timeout=0.01).run("sleep 600")
            assert asdict(raised.value.result) == {"exit_code": -1, "oom_killed": None}

        async def it_raises_a_timeout_holding_what_the_run_left(
            runner: Mock, docker_run: Mock, steps: list[str], output: Path
        ) -> None:
            docker_run.side_effect = hang_forever(steps)
            with pytest.raises(Timeout) as raised:
                await Botbox(runner, timeout=0.01).run("sleep 600", output=output)
            assert (output / "stdout.txt").read_bytes() == b"partial\n"
            assert (output / "stderr.txt").read_bytes() == b"err\n"
            assert raised.value.seconds == 0.01
            assert raised.value.result.exit_code == -1

        async def it_tears_down_in_order(
            runner: Mock, docker_run: Mock, steps: list[str], output: Path
        ) -> None:
            docker_run.side_effect = hang_forever(steps)
            with pytest.raises(Timeout):
                await Botbox(runner, timeout=0.01).run("sleep 600", output=output)
            assert run_steps(steps) == [
                "start proxy",
                "run agent",
                f"remove {AGENT}",
                "settle",
                f"warned: remove its agent container {AGENT}",
                "stop proxy",
                "settle",
                "remove temp directory",
                "warned: remove its temp directory",
            ]

        async def it_takes_the_calls_timeout_over_the_boxs(
            runner: Mock, docker_run: Mock, steps: list[str], output: Path
        ) -> None:
            docker_run.side_effect = hang_forever(steps)
            with pytest.raises(Timeout) as raised:
                await Botbox(runner, timeout=600).run("sleep 600", output=output, timeout=0.01)
            assert raised.value.seconds == 0.01

        async def it_returns_a_run_that_ends_in_time(runner: Mock, output: Path) -> None:
            result = await Botbox(runner, timeout=60).run("true", output=output)
            assert result.exit_code == 3

        async def it_starts_the_clock_once_the_image_is_built(
            runner: Mock, docker_build: Mock, output: Path
        ) -> None:
            async def slow_build(*_args: object, **_options: object) -> None:
                await asyncio.sleep(0.05)

            docker_build.side_effect = slow_build
            result = await Botbox(runner, timeout=0.02).run("true", output=output)
            assert result.exit_code == 3

        async def it_holds_no_exit_code_when_the_agent_never_started(
            runner: Mock, lockdown: Mock, output: Path
        ) -> None:
            lockdown.side_effect = stuck_lockdown
            with pytest.raises(Timeout) as raised:
                await Botbox(runner, timeout=0.01).run("true", output=output)
            assert raised.value.result.exit_code == -1

        async def it_lets_another_timeout_error_through(
            runner: Mock, docker_run: Mock, output: Path
        ) -> None:
            docker_run.side_effect = TimeoutError("docker hung")
            with pytest.raises(TimeoutError, match="docker hung") as raised:
                await Botbox(runner, timeout=60).run("true", output=output)
            assert type(raised.value) is TimeoutError

        @pytest.mark.parametrize("seconds", [0, -1])
        async def it_refuses_a_timeout_that_is_not_positive_before_building(
            runner: Mock, docker_build: Mock, seconds: float, output: Path
        ) -> None:
            with pytest.raises(ValueError, match="timeout"):
                await Botbox(runner).run("true", output=output, timeout=seconds)
            docker_build.assert_not_called()


@pytest.fixture
def held(steps: list[str]) -> Mock:
    """The live session `hold_session` yields: its CLI exits 3 once input ends."""
    live = Mock()

    def end_input() -> None:
        steps.append("end input")
        live.client.set_result(3)

    live.stdin.close.side_effect = end_input
    return live


@pytest.fixture(autouse=True)
def hold_session(held: Mock, steps: list[str]) -> Iterator[Mock]:
    @asynccontextmanager
    async def hold(
        agent: Any, _image: str, _command: Any, *, scratch: Path, name: str, **_: Any
    ) -> AsyncIterator[tuple[Mock, Mock]]:
        held.agent = agent
        held.client = asyncio.get_running_loop().create_future()
        (scratch / "stderr.txt").write_bytes(b"err\n")
        steps.append("hold session")
        try:
            container = Mock()
            container.name = name
            yield held, container
        finally:
            steps.append("release session")

    with patch("botbox.Botbox.hold_session", autospec=True, side_effect=hold) as m:
        yield m


def session_options(hold_session: Mock) -> dict[str, Any]:
    """`hold_session`'s options, with its image and command."""
    [_agent, image, command] = hold_session.call_args.args
    return {**hold_session.call_args.kwargs, "image": image, "command": list(command)}


def describe_session() -> None:
    @pytest.fixture
    def talker(runner: Mock) -> Mock:
        runner.dockerfile = Path("/agents/D")
        runner.session_command.return_value = "an-agent --stream"
        return runner

    async def it_yields_the_held_session_and_leaves_its_result(talker: Mock, held: Mock) -> None:
        box = Botbox(talker)
        async with box.session() as live:
            assert live is held
            assert box.result is None
        assert box.result is not None
        assert box.result is ENDED

    async def it_refuses_a_second_session_while_one_is_open(talker: Mock, steps: list[str]) -> None:
        box = Botbox(talker)
        async with box.session():
            held_so_far = list(steps)
            with pytest.raises(RuntimeError, match="already has an open session"):
                async with box.session():
                    pass
            assert steps == held_so_far
        assert box.result is ENDED

    async def it_refuses_a_second_session_entered_alongside(talker: Mock) -> None:
        box = Botbox(talker)

        async def talk() -> None:
            async with box.session():
                await asyncio.sleep(0)

        outcomes = await asyncio.gather(talk(), talk(), return_exceptions=True)
        assert outcomes[0] is None
        assert isinstance(outcomes[1], RuntimeError)

    async def it_opens_another_session_once_one_is_left(talker: Mock) -> None:
        box = Botbox(talker)
        async with box.session():
            pass
        async with box.session():
            assert box.result is None
        assert box.result is ENDED

    async def it_opens_another_session_once_one_fails(talker: Mock) -> None:
        box = Botbox(talker)
        with pytest.raises(ValueError, match="boom"):
            async with box.session():
                raise ValueError("boom")
        async with box.session():
            pass
        assert box.result is ENDED

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

    async def it_names_its_temp_directory_after_the_run_token_and_locks_it_down(
        talker: Mock, temporary_directory: Mock, lockdown: Mock, scratch: Path
    ) -> None:
        async with Botbox(talker, allow=["registry.npmjs.org"]).session():
            pass
        temporary_directory.assert_called_once_with(prefix=f"botbox-{TOKEN}-")
        assert not (scratch / "home").exists()
        lockdown.assert_called_once_with(
            ("api.anthropic.com", "registry.npmjs.org"),
            scratch,
            TOKEN,
            None,
            credential=None,
            labels={},
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
            "remove temp directory",
            "warned: remove its temp directory",
        ]

    async def it_reads_the_exit_code_with_the_command_client_and_stderr(
        talker: Mock, hold_session: Mock, agent_exit: Mock
    ) -> None:
        async with Botbox(talker).session():
            pass
        [container, client, stderr] = agent_exit.call_args.args
        assert (container.name, client, stderr) == (AGENT, 3, "err\n")
        assert hold_session.call_args.args[0] is talker
        assert hold_session.call_args.kwargs["home"] == staged()

    def describe_the_agent_container() -> None:
        async def it_caps_session_agent_memory(talker: Mock, hold_session: Mock) -> None:
            async with Botbox(talker, memory="64m").session():
                pass
            assert session_options(hold_session)["memory"] == "64m"

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
            assert options["labels"] == {"botbox.run": TOKEN}
            assert "rm" not in options

        async def it_merges_caller_labels_into_the_session_container(
            talker: Mock, hold_session: Mock
        ) -> None:
            async with Botbox(talker, labels={"test.run": LABEL_VALUE}).session():
                pass
            assert session_options(hold_session)["labels"] == {
                "test.run": LABEL_VALUE,
                "botbox.run": TOKEN,
            }

        async def it_merges_env_labels_into_the_session_container(
            talker: Mock, hold_session: Mock
        ) -> None:
            os.environ["BOTBOX_LABELS"] = f"env.run={LABEL_VALUE}"
            async with Botbox(talker).session():
                pass
            assert session_options(hold_session)["labels"] == {
                "env.run": LABEL_VALUE,
                "botbox.run": TOKEN,
            }

        @pytest.mark.parametrize(("uid", "gid"), [(1003, 1005), (2456, 3456)])
        async def it_runs_the_agent_as_the_host_user(
            talker: Mock, hold_session: Mock, monkeypatch: pytest.MonkeyPatch, uid: int, gid: int
        ) -> None:
            monkeypatch.setattr(os, "getuid", lambda: uid)
            monkeypatch.setattr(os, "getgid", lambda: gid)
            async with Botbox(talker).session():
                pass
            assert session_options(hold_session)["user"] == f"{uid}:{gid}"

        async def it_is_locked_down_like_a_run(talker: Mock, hold_session: Mock) -> None:
            async with Botbox(talker).session(workdir="/home/user/src"):
                pass
            options = session_options(hold_session)
            assert options["network"] == "none"
            assert options["pid"] == f"container:{PROXY}"
            assert options["user"] == f"{os.getuid()}:{os.getgid()}"
            assert options["cap_drop"] == ["ALL"]
            assert options["security_opt"] == ["no-new-privileges"]
            assert options["log_driver"] == "none"
            assert options["env"] == {
                "HOME": "/home/user",
                **staged_env(),
                "HTTPS_PROXY": "http://127.0.0.1:41893",
            }
            assert options["workdir"] == "/home/user/src"
            assert options["mounts"] == [
                FakeMount("volume", "botbox-run-0123456789ab", "/run/botbox", read_only=True),
                FakeMount("bind", "/src", "/home/user/src", read_only=True),
            ]

    def describe_failure() -> None:
        async def it_lets_a_failed_docker_command_through_after_tearing_down(
            talker: Mock, agent_exit: Mock, steps: list[str]
        ) -> None:
            failed = CommandFailed()
            agent_exit.side_effect = failed
            with pytest.raises(CommandFailed) as raised:
                box = Botbox(talker)
                async with box.session():
                    pass
            assert raised.value is failed
            assert f"remove {AGENT}" in steps
            assert steps[-1] == "warned: remove its temp directory"
            assert box.result is not None
            assert asdict(box.result) == {"exit_code": -1, "oom_killed": None}

        async def it_tears_down_without_ending_input_when_the_block_fails(
            talker: Mock, steps: list[str]
        ) -> None:
            with pytest.raises(ValueError, match="boom"):
                box = Botbox(talker)
                async with box.session():
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
                "remove temp directory",
                "warned: remove its temp directory",
            ]
            assert box.result is not None
            assert box.result.exit_code == -1

        async def it_tears_down_when_cancelled_mid_turn(talker: Mock, steps: list[str]) -> None:
            talking = asyncio.Event()
            box = Botbox(talker)

            async def talk() -> None:
                async with box.session():
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
                "remove temp directory",
                "warned: remove its temp directory",
            ]
            assert box.result is not None
            assert box.result.exit_code == -1

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
            assert steps[-1] == "warned: remove its temp directory"

        async def it_removes_no_container_when_the_lockdown_fails(
            talker: Mock, lockdown: Mock, hold_session: Mock, steps: list[str]
        ) -> None:
            lockdown.side_effect = RuntimeError("proxy never came up")
            with pytest.raises(RuntimeError, match="proxy never came up"):
                async with Botbox(talker).session():
                    pass
            hold_session.assert_not_called()
            assert not [step for step in steps if step.startswith("remove botbox-agent")]
            assert steps[-1] == "warned: remove its temp directory"

        async def it_builds_and_starts_nothing_when_staging_fails(
            talker: Mock, docker_build: Mock, temporary_directory: Mock
        ) -> None:
            talker.stage_auth.side_effect = PermissionError("no credentials")
            with pytest.raises(PermissionError):
                async with Botbox(talker).session():
                    pass
            docker_build.assert_not_called()
            temporary_directory.assert_not_called()

    def describe_timeout() -> None:
        async def it_raises_a_timeout_holding_what_the_session_left(
            talker: Mock, steps: list[str]
        ) -> None:
            with pytest.raises(Timeout) as raised:
                box = Botbox(talker, timeout=0.01)
                async with box.session():
                    await asyncio.Event().wait()
            assert raised.value.seconds == 0.01
            assert raised.value.result == box.result
            assert box.result is not None
            assert box.result.exit_code == -1
            assert run_steps(steps) == [
                "start proxy",
                "hold session",
                "release session",
                f"remove {AGENT}",
                "settle",
                f"warned: remove its agent container {AGENT}",
                "stop proxy",
                "settle",
                "remove temp directory",
                "warned: remove its temp directory",
            ]

        async def it_times_the_whole_block_not_each_step(talker: Mock) -> None:
            with pytest.raises(Timeout):
                async with Botbox(talker, timeout=0.05).session():
                    for _ in range(50):
                        await asyncio.sleep(0.01)

        async def it_times_the_wait_for_the_cli_to_exit(talker: Mock, held: Mock) -> None:
            held.stdin.close.side_effect = None
            with pytest.raises(Timeout):
                async with Botbox(talker, timeout=0.01).session():
                    pass

        async def it_takes_the_calls_timeout_over_the_boxs(talker: Mock) -> None:
            with pytest.raises(Timeout) as raised:
                async with Botbox(talker, timeout=600).session(timeout=0.01):
                    await asyncio.Event().wait()
            assert raised.value.seconds == 0.01

        async def it_leaves_a_session_that_ends_in_time(talker: Mock) -> None:
            box = Botbox(talker, timeout=60)
            async with box.session():
                pass
            assert box.result is not None
            assert box.result.exit_code == 3

        async def it_holds_no_exit_code_when_the_session_never_started(
            talker: Mock, lockdown: Mock
        ) -> None:
            lockdown.side_effect = stuck_lockdown
            with pytest.raises(Timeout) as raised:
                async with Botbox(talker, timeout=0.01).session():
                    pass
            assert raised.value.result.exit_code == -1

        async def it_lets_another_timeout_error_through(talker: Mock) -> None:
            with pytest.raises(TimeoutError, match="docker hung") as raised:
                async with Botbox(talker, timeout=60).session():
                    raise TimeoutError("docker hung")
            assert type(raised.value) is TimeoutError

        @pytest.mark.parametrize("seconds", [0, -1])
        async def it_refuses_a_timeout_that_is_not_positive_before_building(
            talker: Mock, docker_build: Mock, seconds: float
        ) -> None:
            with pytest.raises(ValueError, match="timeout"):
                async with Botbox(talker).session(timeout=seconds):
                    pass
            docker_build.assert_not_called()

    def describe_output() -> None:
        async def it_routes_streams_proxy_and_transcripts_into_the_output(
            talker: Mock, hold_session: Mock, lockdown: Mock, scratch: Path, tmp_path: Path
        ) -> None:
            async with Botbox(talker).session(output=tmp_path):
                pass
            options = session_options(hold_session)
            assert (options["scratch"], options["output"]) == (scratch, tmp_path)
            lockdown.assert_called_once_with(
                ("api.anthropic.com",), scratch, TOKEN, tmp_path, credential=None, labels={}
            )
            transcripts = FakeMount(
                "bind", str(tmp_path / "transcripts"), "/home/user/.claude/projects"
            )
            assert options["mounts"][-1] == transcripts

        async def it_leaves_only_the_exit_code_in_the_result(
            talker: Mock, agent_exit: Mock, tmp_path: Path
        ) -> None:
            (tmp_path / "stdout.txt").write_text("old")
            (tmp_path / "keep").write_text("keep")
            box = Botbox(talker)
            async with box.session(output=tmp_path):
                pass
            assert agent_exit.call_args.args[2] == "err\n"
            assert box.result is not None
            assert box.result.exit_code == 3
            assert (tmp_path / "stdout.txt").read_bytes() == b""
            assert (tmp_path / "keep").read_text() == "keep"

        async def it_rejects_a_path_docker_cannot_mount_before_building(
            talker: Mock, docker_build: Mock, tmp_path: Path
        ) -> None:
            with pytest.raises(ValueError, match="contains ':'"):
                async with Botbox(talker).session(output=tmp_path / "a:b"):
                    pass
            docker_build.assert_not_called()

        async def it_holds_no_exit_code_when_the_session_times_out(
            talker: Mock, tmp_path: Path
        ) -> None:
            with pytest.raises(Timeout) as raised:
                async with Botbox(talker, timeout=0.01).session(output=tmp_path):
                    await asyncio.Event().wait()
            assert raised.value.result.exit_code == -1


@pytest.fixture
def file_run(docker_run: Mock) -> Mock:
    return docker_run


@pytest.fixture
def setup_failures(runner: Mock, docker_build: Mock, lockdown: Mock) -> dict[str, Mock]:
    return {"build": docker_build, "staging": runner.stage_auth, "proxy": lockdown}


def describe_run_output() -> None:
    @pytest.mark.parametrize("form", ["path", "string", "relative"])
    async def it_writes_the_streams_to_the_output_and_the_temp_home(
        runner: Mock, agent_exit: Mock, scratch: Path, tmp_path: Path, form: str
    ) -> None:
        output = tmp_path / "nested" / "output"
        destination: dict[str, str | Path] = {
            "path": output,
            "string": str(output),
            "relative": os.path.relpath(output),
        }
        result = await Botbox(runner).run("true", output=destination[form])
        assert result.exit_code == 3
        assert (output / "stdout.txt").read_bytes() == b"out\xff\n"
        assert (output / "stderr.txt").read_bytes() == b"err\n"
        assert (scratch / "stdout.txt").read_bytes() == b"out\xff\n"
        assert agent_exit.call_args.args[2] == "err\n"

    async def it_mounts_transcripts_over_the_sessions_dir(
        runner: Mock, file_run: Mock, output: Path
    ) -> None:
        await Botbox(runner).run("true", output=output)
        assert file_run.call_args.kwargs["mounts"] == [
            FakeMount("volume", "botbox-run-0123456789ab", "/run/botbox", read_only=True),
            FakeMount("bind", "/src", "/home/user/src", read_only=True),
            FakeMount("bind", str(output / "transcripts"), "/home/user/.claude/projects"),
        ]
        files = {p.name for p in output.iterdir()}
        assert files == {"stderr.txt", "stdout.txt", "proxy.log", "transcripts"}

    @pytest.mark.usefixtures("file_run")
    async def it_logs_the_proxy_into_the_output(
        runner: Mock, lockdown: Mock, scratch: Path, tmp_path: Path
    ) -> None:
        await Botbox(runner).run("true", output=tmp_path / "output")
        lockdown.assert_called_once_with(
            ("api.anthropic.com",), scratch, TOKEN, tmp_path / "output", credential=None, labels={}
        )

    @pytest.mark.usefixtures("file_run")
    async def it_truncates_streams_but_preserves_other_files(runner: Mock, tmp_path: Path) -> None:
        (tmp_path / "stdout.txt").write_text("old stdout contents")
        (tmp_path / "stderr.txt").write_text("old stderr contents")
        (tmp_path / "proxy.log").write_text("old proxy log")
        (tmp_path / "keep").write_text("keep")
        (tmp_path / "transcripts").mkdir()
        (tmp_path / "transcripts" / "old.jsonl").write_text("old")
        await Botbox(runner).run("true", output=tmp_path)
        assert (tmp_path / "transcripts" / "old.jsonl").read_text() == "old"
        assert (tmp_path / "proxy.log").read_bytes() == b""
        assert (tmp_path / "stdout.txt").read_bytes() == b"out\xff\n"
        assert (tmp_path / "stderr.txt").read_bytes() == b"err\n"
        assert (tmp_path / "keep").read_text() == "keep"

    async def it_rejects_a_path_docker_cannot_mount_before_touching_anything(
        runner: Mock, docker_build: Mock, tmp_path: Path
    ) -> None:
        output = tmp_path / "a:b"
        output.mkdir()
        (output / "stdout.txt").write_text("previous")
        with pytest.raises(ValueError, match="contains ':'"):
            await Botbox(runner).run("true", output=output)
        assert (output / "stdout.txt").read_text() == "previous"
        assert not (output / "transcripts").exists()
        docker_build.assert_not_called()

    @pytest.mark.parametrize("phase", ["build", "staging", "proxy"])
    async def it_clears_previous_streams_before_setup_can_fail(
        runner: Mock,
        setup_failures: dict[str, Mock],
        tmp_path: Path,
        phase: str,
        docker_run: Mock,
    ) -> None:
        (tmp_path / "stdout.txt").write_text("previous stdout")
        (tmp_path / "stderr.txt").write_text("previous stderr")
        (tmp_path / "proxy.log").write_text("previous proxy log")
        setup_failures[phase].side_effect = RuntimeError("setup failed")
        with pytest.raises(RuntimeError, match="setup failed"):
            await Botbox(runner).run("true", output=tmp_path)
        assert (tmp_path / "stdout.txt").read_bytes() == b""
        assert (tmp_path / "stderr.txt").read_bytes() == b""
        assert (tmp_path / "proxy.log").read_bytes() == b""
        docker_run.assert_not_called()

    async def it_removes_the_temp_home_when_docker_raises(
        runner: Mock, file_run: Mock, tmp_path: Path, temporary_directory: Mock
    ) -> None:
        file_run.side_effect = OSError("cannot start")
        with pytest.raises(OSError, match="cannot start"):
            await Botbox(runner).run("true", output=tmp_path)
        temporary_directory.return_value.cleanup.assert_called_once()


@pytest.fixture
def output(tmp_path: Path, file_run: Mock) -> Path:
    file_run.assert_not_called()
    return tmp_path / "output"


class Expired(Exception):
    """Stands in for `CredentialsExpired`."""


@pytest.fixture
def source(steps: list[str]) -> Mock:
    """A host credential the proxy injects."""

    def read() -> Mock:
        steps.append("read credential")
        return Mock(secret="Bearer real")

    return Mock(read=Mock(side_effect=read), env={"ANTHROPIC_BASE_URL": "http://proxy"})


@pytest.fixture
def injector(runner: Mock, source: Mock) -> Mock:
    """An agent whose credential the proxy injects, with a session mode."""
    runner.dockerfile = Path("/agents/D")
    runner.allow = ()
    runner.credential_source = source
    runner.session_command.return_value = "an-agent --stream"
    return runner


@pytest.fixture
def credentials(jail: Mock, steps: list[str]) -> Mock:
    """The jail's credential proxy, following the host's credential inside its block."""

    @asynccontextmanager
    async def following(*_args: object) -> AsyncIterator[None]:
        steps.append("follow credential")
        try:
            yield
        finally:
            steps.append("stop following")

    credentials = Mock(following=Mock(side_effect=following))
    jail.credentials = credentials
    return credentials


async def run_and_talk(box: Botbox, how: str) -> None:
    if how == "run":
        await box.run("true")
        return
    async with box.session():
        pass


def agent_env(how: str, docker_run: Mock, hold_session: Mock) -> dict[str, str]:
    options = docker_run.call_args.kwargs if how == "run" else hold_session.call_args.kwargs
    env: dict[str, str] = options["env"]
    return env


@pytest.mark.parametrize("how", ["run", "session"])
def describe_credential_injection() -> None:
    async def it_reads_the_credential_before_building(
        injector: Mock, steps: list[str], how: str
    ) -> None:
        await run_and_talk(Botbox(injector), how)
        assert steps.index("read credential") < steps.index("build an-agent:latest")
        injector.credential_source.read.assert_called_once_with()

    async def it_starts_nothing_when_the_host_login_has_expired(
        injector: Mock,
        docker_build: Mock,
        lockdown: Mock,
        temporary_directory: Mock,
        how: str,
    ) -> None:
        injector.credential_source.read.side_effect = Expired("expired")
        with pytest.raises(Expired):
            await run_and_talk(Botbox(injector), how)
        docker_build.assert_not_called()
        temporary_directory.assert_not_called()
        lockdown.assert_not_called()

    async def it_has_the_proxy_send_the_credential(
        injector: Mock, lockdown: Mock, scratch: Path, how: str
    ) -> None:
        await run_and_talk(Botbox(injector), how)
        credential = lockdown.call_args.kwargs["credential"]
        assert credential.secret == "Bearer real"
        assert lockdown.call_args.args == ((), scratch, TOKEN, None)

    @pytest.mark.usefixtures("credentials")
    async def it_follows_the_host_credential_while_the_agent_runs(
        injector: Mock, steps: list[str], how: str
    ) -> None:
        await run_and_talk(Botbox(injector), how)
        agent = "run agent" if how == "run" else "hold session"
        ordered = [
            s for s in steps if s in {"start proxy", "follow credential", agent, "stop following"}
        ]
        assert ordered == ["start proxy", "follow credential", agent, "stop following"]
        assert steps.index("stop following") < steps.index("stop proxy")

    async def it_follows_from_the_secret_the_proxy_started_with(
        injector: Mock, credentials: Mock, how: str
    ) -> None:
        await run_and_talk(Botbox(injector), how)
        credentials.following.assert_called_once_with(injector.credential_source, "Bearer real")

    @pytest.mark.usefixtures("credentials")
    async def it_points_the_agent_at_the_proxy(
        injector: Mock, docker_run: Mock, hold_session: Mock, how: str
    ) -> None:
        await run_and_talk(Botbox(injector), how)
        assert agent_env(how, docker_run, hold_session) == {
            "HOME": "/home/user",
            **staged_env(),
            "HTTPS_PROXY": "http://127.0.0.1:41893",
            "ANTHROPIC_BASE_URL": "http://proxy",
        }

    async def it_points_nowhere_and_follows_nothing_without_a_credential_proxy(
        injector: Mock, docker_run: Mock, hold_session: Mock, steps: list[str], how: str
    ) -> None:
        await run_and_talk(Botbox(injector), how)
        assert "ANTHROPIC_BASE_URL" not in agent_env(how, docker_run, hold_session)
        assert "follow credential" not in steps

    async def it_injects_nothing_for_an_agent_with_no_source(
        injector: Mock, lockdown: Mock, credentials: Mock, how: str
    ) -> None:
        injector.credential_source = None
        await run_and_talk(Botbox(injector), how)
        assert lockdown.call_args.kwargs == {"credential": None, "labels": {}}
        credentials.following.assert_not_called()
