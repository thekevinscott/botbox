"""`AsyncBotbox.run()` against a fake `docker` on PATH that keeps each container's state."""

import asyncio
import json
import os
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from botbox import AsyncBotbox, ClaudeAgent, DockerException, RunResult

CREDENTIALS = '{"claudeAiOauth": {"accessToken": "t"}}'
REFUSAL = 'NOTICE Proxying refused on filtered url "github.com:443"\n'

# Each container is a state file, `<name>.json`, that inspect reads and rm deletes. The proxy
# serves until its stdin closes; each agent does what the plan says for its command.
FAKE_DOCKER = """
import json, os, signal, sys, time
from pathlib import Path

argv = sys.argv[1:]
state = Path(os.environ["FAKE_DOCKER_STATE"])
plan = json.loads((state / "plan.json").read_text())
with open(state / "calls.jsonl", "a") as log:
    log.write(json.dumps(argv) + "\\n")


def fail(message, code=1):
    sys.stderr.write(message)
    sys.exit(code)


def option(name):
    return argv[argv.index(name) + 1]


def volume(target):
    mounts = (argv[i + 1].split(":") for i, a in enumerate(argv) if a == "--volume")
    return next(Path(source) for source, t, _ in mounts if t == target)


def settle(name, status, code=0):
    (state / f"{name}.json").write_text(json.dumps({"Status": status, "ExitCode": code}))


command = argv[0]
if command == "buildx":
    sys.exit(0)
if (state / "down").exists():
    fail("Cannot connect to the Docker daemon\\n")
if command == "version":
    print("{}")
elif command == "container":
    name = argv[-1]
    path = state / f"{name}.json"
    if not path.exists():
        fail(f"Error: No such container: {name}\\n")
    print(json.dumps([{"Name": "/" + name, "State": json.loads(path.read_text())}]))
elif command == "rm":
    time.sleep(plan.get("rm_seconds", 0))
    if plan.get("rm_fails"):
        fail("Error response from daemon: removal of container is already in progress\\n")
    (state / f"{argv[-1]}.json").unlink(missing_ok=True)
elif option("--name").startswith("botbox-proxy-"):
    name = option("--name")
    if plan.get("proxy_fails"):
        fail("tinyproxy: bad config\\n")
    settle(name, "running")
    log = volume("/var/log/tinyproxy") / "tinyproxy.log"
    log.write_bytes(plan.get("proxy_log", "").encode("latin-1"))
    if plan.get("proxy_log_unreadable"):
        log.unlink()
        log.mkdir()
    (volume("/run/botbox") / "proxy.sock").touch()
    sys.stdin.buffer.read()
    settle(name, "exited")
else:
    name = option("--name")
    agent = plan["agents"].get(argv[-1], {})
    if agent.get("missing"):
        fail("Unable to find image 'botbox-claude:latest' locally\\n", 125)
    settle(name, "running")
    session = volume("/home/user") / ".claude" / "projects" / "-work"
    session.mkdir(parents=True)
    (session / "abc.jsonl").write_text('{"type": "user"}\\n')
    sys.stdout.write(agent.get("stdout", ""))
    sys.stderr.write(agent.get("stderr", ""))
    sys.stdout.flush()
    sys.stderr.flush()
    mode = agent.get("mode")
    if mode == "hang":
        (state / f"{name}.hanging").touch()
        time.sleep(600)
    if mode == "daemon_gone":
        (state / "down").touch()
        sys.exit(125)
    if mode == "client_dies":
        os.kill(os.getpid(), signal.SIGKILL)
    if mode == "client_dies_after_exit":
        settle(name, "exited", 0)
        os.kill(os.getpid(), signal.SIGKILL)
    settle(name, "exited", agent.get("exit", 0))
    sys.exit(agent.get("exit", 0))
"""


class Daemon:
    """What the fake `docker` was asked, the containers it holds, and the plan it follows."""

    def __init__(self, state: Path) -> None:
        self.state = state
        self.plan: dict[str, Any] = {"agents": {}}
        self.save()

    def save(self) -> None:
        (self.state / "plan.json").write_text(json.dumps(self.plan))

    def agent(self, command: str, **behaviour: Any) -> None:
        self.plan["agents"][command] = behaviour
        self.save()

    def set(self, **options: Any) -> None:
        self.plan.update(options)
        self.save()

    @property
    def calls(self) -> list[list[str]]:
        log = self.state / "calls.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def runs(self, prefix: str) -> list[list[str]]:
        return [
            c for c in self.calls if c[0] == "run" and c[c.index("--name") + 1].startswith(prefix)
        ]

    @property
    def containers(self) -> list[str]:
        """The containers the daemon still holds."""
        return sorted(p.stem for p in self.state.glob("botbox-*.json"))

    @property
    def removed(self) -> list[str]:
        return [c[-1] for c in self.calls if c[0] == "rm"]

    async def hanging(self, count: int = 1) -> None:
        async with asyncio.timeout(10):
            while len(list(self.state.glob("*.hanging"))) < count:
                await asyncio.sleep(0.01)


@pytest.fixture(autouse=True)
def docker() -> Iterator[None]:
    """Overrides conftest's: asyncio spawns through the `subprocess.Popen` it patches."""
    with patch("python_on_whales.utils.run", autospec=True):
        yield


@pytest.fixture(autouse=True)
def daemon(tmp_path: Path) -> Iterator[Daemon]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    fake.write_text(f"#!{sys.executable}\n{FAKE_DOCKER}")
    fake.chmod(0o755)
    state = tmp_path / "daemon"
    state.mkdir()
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "FAKE_DOCKER_STATE": str(state)}
    with patch.dict(os.environ, env):
        yield Daemon(state)


@pytest.fixture(autouse=True)
def temp(tmp_path: Path) -> Iterator[Path]:
    """Where the runs' temp homes go."""
    directory = tmp_path / "tmp"
    directory.mkdir()
    with patch.object(tempfile, "tempdir", str(directory)):
        yield directory


@pytest.fixture
def box(tmp_path: Path) -> AsyncBotbox:
    home = tmp_path / "claude-home"
    home.mkdir()
    (home / ".credentials.json").write_text(CREDENTIALS)
    return AsyncBotbox(ClaudeAgent(host_home=home))


def token(daemon: Daemon) -> str:
    [run] = daemon.runs("botbox-agent-")
    return run[run.index("--name") + 1].removeprefix("botbox-agent-")


def homes(temp: Path) -> list[Path]:
    """The temp homes left behind; build locks live beside them for good."""
    return [path for path in temp.iterdir() if path.is_dir()]


def option(run: list[str], name: str) -> str:
    return run[run.index(name) + 1]


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
