import signal
import subprocess
import threading
from collections.abc import Sequence
from contextlib import ExitStack, suppress
from pathlib import Path
from tempfile import TemporaryDirectory
from types import FrameType, TracebackType
from typing import Self
from uuid import uuid4

from python_on_whales import docker
from python_on_whales.exceptions import DockerException

from botbox.agents.agent import Agent, SessionAgent
from botbox.bind_mounts import Mount, bind_mounts
from botbox.build_lock import build_lock
from botbox.build_steps import build_steps
from botbox.collect import collect
from botbox.lockdown import RELAY, SOCKET_DIR, Lockdown, lockdown
from botbox.RunResult import RunResult
from botbox.Session import Session, read_transcript


class Botbox:
    """An agent, an optional image layer on top of it, and the extra hosts its proxy admits.

    Used as a context manager, SIGTERM inside the block raises `SystemExit`, so a run or session
    in progress unwinds and tears down; Python's default SIGTERM exits without unwinding. A
    SIGTERM handler the program set itself is left alone.
    """

    def __init__(
        self,
        agent: Agent,
        *,
        dockerfile: str | Path | None = None,
        allow: Sequence[str] = (),
    ) -> None:
        self.agent = agent
        self.dockerfile = None if dockerfile is None else Path(dockerfile).resolve()
        if isinstance(allow, str):
            raise TypeError(f"allow takes a sequence of hosts: pass allow=({allow!r},)")
        self.allow = tuple(allow)
        self._unwinds = False

    def __enter__(self) -> Self:
        if (
            threading.current_thread() is threading.main_thread()
            and signal.getsignal(signal.SIGTERM) is signal.SIG_DFL
        ):
            signal.signal(signal.SIGTERM, _unwind)
            self._unwinds = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._unwinds:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            self._unwinds = False

    def build(self) -> str:
        """Build the agent's image, then `dockerfile` on top, and return the final tag.

        Built on every call; Docker's layer cache keeps an unchanged build fast. Concurrent
        builds of one tag, from any process, take turns.
        """
        steps = build_steps(self.agent, self.dockerfile)
        for step in steps:
            with build_lock(step.tag):
                docker.build(
                    step.context,
                    tags=step.tag,
                    file=step.file,
                    build_contexts=step.contexts,
                    progress=False,
                )
        return steps[-1].tag

    def run(
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
        A non-zero exit is a normal result; so is the daemon dying mid-run, with `exit_code`
        -1 and whatever output, transcript and proxy log made it to the host. Raises only when
        setup fails or the run is interrupted, after tearing down what was started.

        The container removes itself when it exits; a raising run removes it by name.
        """
        agent = self.agent
        volumes = bind_mounts(mounts, workdir=workdir, home=agent.home)
        image = self.build()
        with TemporaryDirectory(prefix="botbox-") as scratch:
            home = Path(scratch) / "home"
            home.mkdir()
            agent.stage_auth(home)
            with lockdown((*agent.allow, *self.allow), Path(scratch)) as jail:
                # Named up front: killing the client leaves its container running.
                name = _container_name()
                try:
                    stdout, stderr, exit_code = collect(
                        [
                            "docker",
                            "run",
                            *self._lockdown_flags(name, home, jail, volumes, workdir),
                            image,
                            RELAY,
                            "sh",
                            "-c",
                            command,
                        ]
                    )
                except BaseException:
                    with suppress(DockerException):
                        docker.container.remove(name, force=True)
                    raise
            transcript = read_transcript(home, agent.transcripts)
        return RunResult(stdout, stderr, exit_code, transcript, jail.log, image)

    def session(
        self,
        *,
        mounts: Sequence[Mount] = (),
        workdir: str | Path | None = None,
    ) -> Session:
        """Start the agent's CLI in its session mode in the locked-down container and hold it open.

        Same lockdown, home and mounts as `run()`. The container joins the proxy's PID
        namespace, whose init (the proxy's, not the agent's) reaps whatever the agent leaves
        running in the background. The container removes itself when the CLI exits. Raises
        `TypeError` for an agent with no session mode.
        """
        agent = self.agent
        if not isinstance(agent, SessionAgent):
            raise TypeError(f"{type(agent).__name__} has no session mode")
        command = agent.session_command()
        volumes = bind_mounts(mounts, workdir=workdir, home=agent.home)
        image = self.build()
        resources = ExitStack()
        name = None
        try:
            scratch = Path(resources.enter_context(TemporaryDirectory(prefix="botbox-")))
            home = scratch / "home"
            home.mkdir()
            agent.stage_auth(home)
            jail = resources.enter_context(lockdown((*agent.allow, *self.allow), scratch))
            name = _container_name()
            process = subprocess.Popen(
                [
                    "docker",
                    "run",
                    "--interactive",
                    *self._lockdown_flags(name, home, jail, volumes, workdir),
                    image,
                    RELAY,
                    "sh",
                    "-c",
                    command,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except BaseException:
            if name is not None:
                with suppress(DockerException):
                    docker.container.remove(name, force=True)
            resources.close()
            raise

        def finish() -> tuple[dict[str, str], str]:
            transcript = read_transcript(home, agent.transcripts)
            resources.close()
            return transcript, jail.log

        return Session(agent, process, image, finish)

    def _lockdown_flags(
        self,
        name: str,
        home: Path,
        jail: Lockdown,
        volumes: list[tuple[str, str, str]],
        workdir: str | Path | None,
    ) -> list[str]:
        """`docker run` flags for an agent container that removes itself when it exits.

        One attached `docker run`, not create then start: an owner dying in between would leave
        a created container that --rm never removes.
        """
        agent = self.agent
        mounts = [(str(home), agent.home, "rw"), (str(jail.sockets), SOCKET_DIR, "ro"), *volumes]
        return [
            "--rm",
            "--name",
            name,
            *[flag for k, v in jail.envs.items() for flag in ("--env", f"{k}={v}")],
            *[flag for m in mounts for flag in ("--volume", ":".join(m))],
            "--workdir",
            agent.home if workdir is None else Path(workdir).as_posix(),
            "--network",
            "none",
            "--pid",
            f"container:{jail.proxy}",
            "--user",
            "user",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
        ]


def _container_name() -> str:
    return f"botbox-agent-{uuid4().hex[:12]}"


def _unwind(_signum: int, _frame: FrameType | None) -> None:
    raise SystemExit(143)  # 128 + SIGTERM, as a shell reports it
