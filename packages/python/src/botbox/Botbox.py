import asyncio
import os
import signal
import threading
import warnings
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from types import TracebackType
from typing import Any, Self, cast
from uuid import uuid4

from adocker.build import build as docker_build
from adocker.run import run as docker_run
from adocker.volume import volume as docker_volume
from botbox.agent_exit import agent_exit
from botbox.agents.agent import Agent, SessionAgent
from botbox.bind_mounts import Mount, bind_mounts
from botbox.build_steps import build_steps
from botbox.check_timeout import check_timeout
from botbox.hold_session import hold_session
from botbox.lockdown import RELAY, SOCKET_DIR, Lockdown, lockdown
from botbox.process import settle
from botbox.remove_within import remove_within
from botbox.RunResult import RunResult
from botbox.Session import Session
from botbox.stage_home import stage_home
from botbox.Timeout import Timeout
from botbox.warned import warned


class Botbox:
    """An agent, an optional image layer, the extra hosts its proxy admits, and a timeout.

    `timeout` is in seconds and bounds every run and session; None, the default, is no limit.
    A call's own `timeout` takes its place.

    Used as an async context manager, SIGTERM inside the block cancels the task that entered it,
    so a run or session in progress unwinds and tears down, then the block raises
    `SystemExit(143)`; Python's default SIGTERM exits without unwinding. A SIGTERM handler the
    program set itself is left alone, and so is SIGTERM off the main thread.

    Don't fork while a run is in progress: a forked child shares the loop's state and holds
    the run's pipes.
    """

    def __init__(
        self,
        agent: Agent,
        *,
        dockerfile: str | Path | None = None,
        allow: Sequence[str] = (),
        timeout: float | None = None,
    ) -> None:
        if os.getuid() == 0:
            raise RuntimeError("botbox won't run an agent as root: run it as a regular user")
        self.agent = agent
        self.dockerfile = None if dockerfile is None else Path(dockerfile).resolve()
        if isinstance(allow, str):
            raise TypeError(f"allow takes a sequence of hosts: pass allow=({allow!r},)")
        self.allow = tuple(allow)
        self.timeout = check_timeout(timeout)
        self._unwinding: asyncio.Task[Any] | None = None
        self._entry: object | None = None
        self._terminated = False

    async def __aenter__(self) -> Self:
        if (
            threading.current_thread() is threading.main_thread()
            and signal.getsignal(signal.SIGTERM) is signal.SIG_DFL
        ):
            # Never None: __aenter__ only runs inside a task.
            self._unwinding = cast("asyncio.Task[Any]", asyncio.current_task())
            self._entry = object()
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGTERM, self._terminate, self._entry, self._unwinding)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        task = self._unwinding
        if task is None:
            return
        asyncio.get_running_loop().remove_signal_handler(signal.SIGTERM)
        self._unwinding = None
        self._entry = None
        if self._terminated:
            self._terminated = False
            task.uncancel()
            raise SystemExit(143) from exc  # 128 + SIGTERM, as a shell reports it

    def _terminate(self, entry: object, task: asyncio.Task[Any]) -> None:
        """Cancel `task`, the one inside the block, on SIGTERM; leaving it raises `SystemExit`.

        Once per entry, and only while `entry` is the block still open: removing the handler
        doesn't drop a call the loop has already queued.
        """
        if entry is not self._entry or self._terminated:
            return
        self._terminated = True
        task.cancel()

    async def build(self) -> str:
        """Build the agent's image, then `dockerfile` on top, and return the final tag.

        Built on every call; Docker's layer cache keeps an unchanged build fast. Concurrent
        builds of one tag, from any process, all succeed, and the tag ends on whichever finished
        last. Cancelling stops the build in progress. A failed build raises `DockerException`.
        """
        steps = build_steps(self.agent, self.dockerfile)
        for step in steps:
            await docker_build(step.context, tag=step.tag, file=step.file, contexts=step.contexts)
        return steps[-1].tag

    async def run(
        self,
        command: str,
        *,
        output: str | Path,
        mounts: Sequence[Mount] = (),
        workdir: str | Path | None = None,
        timeout: float | None = None,
    ) -> RunResult:
        """Run `command` as `sh -c` in the locked-down container and return its exit code.

        stdout, stderr and the proxy's output go directly to stdout.txt, stderr.txt and
        proxy.log in `output`, and transcripts/ there is mounted over the agent's
        `sessions_dir`. The three files are truncated; other files are kept. A path with `:`
        raises `ValueError`, since Docker can't mount it.

        Mounts, `workdir` and `output` are checked before anything is built. The agent's home is
        a fresh Docker volume with the credentials staged in, removed after the run.
        A non-zero exit is a normal result; so is the daemon going away mid-run, with
        `exit_code` -1.

        Cancelling the task, or an `asyncio.timeout` firing, removes the run's containers and
        volumes before the cancel propagates, through any number of further cancels. Both
        containers and both volumes are labelled `botbox.run=<token>`. Raises `DockerException`
        if setup fails or the container never ran to its exit while the daemon was up. A teardown
        step that fails, or a container removal that takes longer than 30 seconds, is a warning,
        never the error.

        The timeout, `timeout` or else the box's, starts once the image is built. When it runs
        out, the run tears down as a cancel does and raises `Timeout` with `exit_code` -1.
        """
        agent = self.agent
        limit = self.timeout if timeout is None else check_timeout(timeout)
        volumes = bind_mounts(mounts, workdir=workdir, home=agent.home)
        output = self._prepare_output(output, volumes)
        image = await self.build()
        token = uuid4().hex[:12]
        deadline = asyncio.timeout(limit)
        allow = (*agent.allow, *self.allow)
        try:
            async with (
                deadline,
                self._home(image, token) as home,
                lockdown(allow, token, output) as jail,
            ):
                flags = self._lockdown_flags(token, home, jail, volumes, workdir)
                exit_code = await self._attach(
                    token, [*flags, image, RELAY, "sh", "-c", command], output
                )
        except TimeoutError as timed_out:
            if limit is None or not deadline.expired():
                raise
            raise Timeout(limit, RunResult(-1)) from timed_out
        return RunResult(exit_code)

    @asynccontextmanager
    async def session(
        self,
        *,
        output: str | Path,
        mounts: Sequence[Mount] = (),
        workdir: str | Path | None = None,
        timeout: float | None = None,
    ) -> AsyncIterator[Session]:
        """Start the agent's CLI in its session mode in the locked-down container and hold it open.

        The same lockdown, home and mounts as `run()`, with the containers and volumes labelled
        the same way. Leaving the block ends the CLI's input, waits for it to exit,
        removes the session's containers and volumes, and leaves the `RunResult` in the
        session's `result`. Cancelling, or an error out of the block, kills the CLI instead and
        tears down the same way, through any number of further cancels, leaving exit code -1 if
        none was read. Raises `TypeError` for an agent with no session mode, and
        `DockerException` as `run()` does.

        The timeout, `timeout` or else the box's, covers the whole block, from once the image is
        built to the CLI's exit. When it runs out, the session tears down as a cancel does and
        raises `Timeout` with the session's `result`.

        `output` is required, and as for `run()`: the CLI's stdout and stderr, the proxy's output
        and the transcripts go straight to files there. Events are read by following stdout.txt.
        """
        agent = self.agent
        if not isinstance(agent, SessionAgent):
            raise TypeError(f"{type(agent).__name__} has no session mode")
        limit = self.timeout if timeout is None else check_timeout(timeout)
        command = agent.session_command()
        volumes = bind_mounts(mounts, workdir=workdir, home=agent.home)
        output = self._prepare_output(output, volumes)
        image = await self.build()
        token = uuid4().hex[:12]
        live = None
        exit_code = -1
        deadline = asyncio.timeout(limit)
        allow = (*agent.allow, *self.allow)
        try:
            try:
                async with (
                    deadline,
                    self._home(image, token) as home,
                    lockdown(allow, token, output) as jail,
                ):
                    name = f"botbox-agent-{token}"
                    flags = self._lockdown_flags(token, home, jail, volumes, workdir)
                    args = [
                        "--interactive",
                        "--name",
                        name,
                        *flags,
                        image,
                        RELAY,
                        "sh",
                        "-c",
                        command,
                    ]
                    try:
                        async with hold_session(agent, args, output) as live:
                            yield live
                            live.stdin.close()
                            client = await live.client
                        stderr = f"See {output / 'stderr.txt'}"
                        exit_code = await agent_exit(name, ["docker", "run", *args], client, stderr)
                    finally:
                        await settle(
                            warned(remove_within(name), f"remove its agent container {name}")
                        )
            except BaseException:
                if live is not None:
                    live.result = RunResult(exit_code)
                raise
            live.result = RunResult(exit_code)
        except TimeoutError as timed_out:
            if limit is None or not deadline.expired():
                raise
            result = None if live is None else live.result
            if result is None:
                result = RunResult(-1)
            raise Timeout(limit, result) from timed_out

    async def _attach(self, token: str, args: list[str], output: Path) -> int:
        """Run with stdout and stderr in `output`, then remove the agent container."""
        name = f"botbox-agent-{token}"
        args = ["--name", name, *args]
        try:
            with (
                (output / "stdout.txt").open("wb") as stdout,
                (output / "stderr.txt").open("wb") as stderr,
            ):
                client = await docker_run(
                    args, stdin=asyncio.subprocess.DEVNULL, stdout=stdout, stderr=stderr
                )
                diagnostic = f"See {output / 'stderr.txt'}"
                exit_code = await agent_exit(name, ["docker", "run", *args], client, diagnostic)
        finally:
            await settle(warned(remove_within(name), f"remove its agent container {name}"))
        return exit_code

    @asynccontextmanager
    async def _home(self, image: str, token: str) -> AsyncIterator[str]:
        """Yield the run's home volume, staged; leaving removes it, warning if that fails."""
        name = f"botbox-home-{token}"

        def unremoved(error: Exception) -> None:
            warnings.warn(
                f"botbox could not remove its home volume {name}: {error}",
                RuntimeWarning,
                stacklevel=2,
            )

        async with docker_volume(name, label=f"botbox.run={token}", on_error=unremoved):
            await stage_home(self.agent, image, name, token)
            yield name

    def _prepare_output(self, output: str | Path, volumes: list[tuple[str, str, str]]) -> Path:
        """Truncate the stream files in `output` and mount its transcripts/ over `sessions_dir`."""
        output = Path(output).resolve()
        if ":" in str(output):
            raise ValueError(f"output {output} contains ':', which Docker can't mount")
        output.mkdir(parents=True, exist_ok=True)
        (output / "stdout.txt").open("wb").close()
        (output / "stderr.txt").open("wb").close()
        (output / "proxy.log").open("wb").close()
        (output / "transcripts").mkdir(exist_ok=True)
        sessions = f"{self.agent.home}/{self.agent.sessions_dir}"
        volumes.append((str(output / "transcripts"), sessions, "rw"))
        return output

    def _lockdown_flags(
        self,
        token: str,
        home: str,
        jail: Lockdown,
        volumes: list[tuple[str, str, str]],
        workdir: str | Path | None,
    ) -> list[str]:
        """`docker run` flags for an agent container, in the proxy's PID namespace, with no network.

        No `--rm`: the run reads the exit code from the stopped container, then removes it.
        """
        agent = self.agent
        mounts = [(home, agent.home, "rw"), (jail.volume, SOCKET_DIR, "ro"), *volumes]
        return [
            "--label",
            f"botbox.run={token}",
            "--env",
            f"HOME={agent.home}",
            *[flag for k, v in jail.envs.items() for flag in ("--env", f"{k}={v}")],
            *[flag for m in mounts for flag in ("--volume", ":".join(m))],
            "--workdir",
            agent.home if workdir is None else Path(workdir).as_posix(),
            "--network",
            "none",
            "--pid",
            f"container:{jail.proxy}",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--log-driver",
            "none",
        ]
