import asyncio
import os
import signal
import threading
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from types import TracebackType
from typing import Any, Self, cast
from uuid import uuid4

from botbox.agent_exit import agent_exit
from botbox.agents.agent import Agent, SessionAgent
from botbox.bind_mounts import Mount, bind_mounts
from botbox.build_lock import build_lock
from botbox.build_steps import build_steps
from botbox.Claim import Claim
from botbox.docker.build import build as docker_build
from botbox.docker.run import run as docker_run
from botbox.docker.settle import settle
from botbox.hold_session import hold_session
from botbox.lockdown import RELAY, SOCKET_DIR, Lockdown, lockdown
from botbox.read_transcript import read_transcript
from botbox.reap import reap
from botbox.remove_within import remove_within
from botbox.RunResult import RunResult
from botbox.Session import Session
from botbox.session_result import session_result
from botbox.warned import warned


class Botbox:
    """An agent, an optional image layer on top of it, and the extra hosts its proxy admits.

    `memory` (a `docker run --memory` size) and `pids` cap the agent's container; `None` lifts
    either cap. The defaults are deliberately high, so set them to what the agent needs.

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
        memory: str | None = "64g",
        pids: int | None = 32768,
    ) -> None:
        if os.getuid() == 0:
            raise RuntimeError("botbox won't run an agent as root: run it as a regular user")
        self.agent = agent
        self.dockerfile = None if dockerfile is None else Path(dockerfile).resolve()
        if isinstance(allow, str):
            raise TypeError(f"allow takes a sequence of hosts: pass allow=({allow!r},)")
        self.allow = tuple(allow)
        self.memory = memory
        self.pids = pids
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
        builds of one tag, from any process, take turns without blocking the loop. Cancelling
        stops the build in progress. A failed build raises `DockerException`.
        """
        steps = build_steps(self.agent, self.dockerfile)
        for step in steps:
            async with build_lock(step.tag):
                await docker_build(
                    step.context, tag=step.tag, file=step.file, contexts=step.contexts
                )
        return steps[-1].tag

    async def run(
        self,
        command: str,
        *,
        mounts: Sequence[Mount] = (),
        workdir: str | Path | None = None,
    ) -> RunResult:
        """Run `command` as `sh -c` in the locked-down container and return what it left.

        Mounts and `workdir` are checked before anything is built. The agent's home is a fresh
        host temp directory with the credentials staged in; the proxy logs into the same
        directory. Both are read into the result once the container exits, then deleted.
        A non-zero exit is a normal result; so is the daemon going away mid-run, with
        `exit_code` -1.

        Cancelling the task, or an `asyncio.timeout` firing, removes the run's containers and
        temp home before the cancel propagates, through any number of further cancels. Both
        containers are labelled `botbox.run=<token>`, and the temp home is `<token>` in a
        per-user dir under the system temp dir. A run first sweeps up after runs whose owner
        died (see `reap()`). Raises `DockerException` if setup fails or the container never ran
        to its exit while the daemon was up. A teardown step that fails, or a container removal
        that takes longer than 30 seconds, is a warning, never the error.
        """
        agent = self.agent
        volumes = bind_mounts(mounts, workdir=workdir, home=agent.home)
        await reap()
        image = await self.build()
        token = uuid4().hex[:12]
        claim = Claim(token)
        try:
            home = claim.path / "home"
            # Owner-only, so an agent under another uid can't leave files the host can't delete.
            home.mkdir(mode=0o700)
            agent.stage_auth(home)
            allow = (*agent.allow, *self.allow)
            async with lockdown(allow, claim.path, token) as jail:
                flags = self._lockdown_flags(token, home, jail, volumes, workdir)
                stdout, stderr, exit_code = await self._attach(
                    token, [*flags, image, RELAY, "sh", "-c", command]
                )
                transcript = await asyncio.to_thread(read_transcript, home, agent.transcripts)
        finally:
            await settle(warned(asyncio.to_thread(claim.cleanup), "remove its temp home"))
        return RunResult(stdout, stderr, exit_code, transcript, jail.log, image)

    @asynccontextmanager
    async def session(
        self,
        *,
        mounts: Sequence[Mount] = (),
        workdir: str | Path | None = None,
    ) -> AsyncIterator[Session]:
        """Start the agent's CLI in its session mode in the locked-down container and hold it open.

        The same lockdown, home and mounts as `run()`, with the container labelled and its temp
        home named the same way. Leaving the block ends the CLI's input, waits for it to exit,
        removes the session's containers and temp home, and leaves the `RunResult` in the
        session's `result`. Cancelling, or an error out of the block, kills the CLI instead and
        tears down the same way, through any number of further cancels. The result retains
        available artifacts on these paths too, with exit code -1 if no exit code was read.
        Artifact read failures warn without replacing the original error. Raises `TypeError` for
        an agent with no session mode, and `DockerException` as `run()` does.
        """
        agent = self.agent
        if not isinstance(agent, SessionAgent):
            raise TypeError(f"{type(agent).__name__} has no session mode")
        command = agent.session_command()
        volumes = bind_mounts(mounts, workdir=workdir, home=agent.home)
        await reap()
        image = await self.build()
        token = uuid4().hex[:12]
        claim = Claim(token)
        live = None
        exit_code = -1
        try:
            home = claim.path / "home"
            home.mkdir(mode=0o700)
            agent.stage_auth(home)
            allow = (*agent.allow, *self.allow)
            async with lockdown(allow, claim.path, token) as jail:
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
                    async with hold_session(agent, args) as live:
                        yield live
                        live.stdin.close()
                        client = await live.client
                    stderr = live.stderr.decode(errors="replace")
                    exit_code = await agent_exit(name, ["docker", "run", *args], client, stderr)
                finally:
                    await settle(warned(remove_within(name), f"remove its agent container {name}"))
        finally:
            try:
                if live is not None:
                    await settle(
                        warned(
                            session_result(live, home, jail.log, image, exit_code),
                            "read its session artifacts",
                        )
                    )
            finally:
                await settle(warned(asyncio.to_thread(claim.cleanup), "remove its temp home"))

    async def _attach(self, token: str, args: list[str]) -> tuple[str, str, int]:
        """Run the agent container to its exit, remove it, and return its output and exit code."""
        name = f"botbox-agent-{token}"
        args = ["--name", name, *args]
        out, err = bytearray(), bytearray()
        try:
            client = await docker_run(
                args, stdin=asyncio.subprocess.DEVNULL, stdout=out, stderr=err
            )
            stderr = err.decode(errors="replace")
            exit_code = await agent_exit(name, ["docker", "run", *args], client, stderr)
        finally:
            await settle(warned(remove_within(name), f"remove its agent container {name}"))
        return out.decode(errors="replace"), stderr, exit_code

    def _lockdown_flags(
        self,
        token: str,
        home: Path,
        jail: Lockdown,
        volumes: list[tuple[str, str, str]],
        workdir: str | Path | None,
    ) -> list[str]:
        """`docker run` flags for an agent container, in the proxy's PID namespace, with no network.

        No `--rm`: the run reads the exit code from the stopped container, then removes it.
        """
        agent = self.agent
        mounts = [(str(home), agent.home, "rw"), (str(jail.sockets), SOCKET_DIR, "ro"), *volumes]
        caps = [
            *([] if self.memory is None else ["--memory", self.memory]),
            *([] if self.pids is None else ["--pids-limit", str(self.pids)]),
        ]
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
            *caps,
        ]
