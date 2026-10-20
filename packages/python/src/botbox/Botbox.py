import hashlib
import subprocess
from collections.abc import Sequence
from contextlib import ExitStack, suppress
from pathlib import Path
from tempfile import TemporaryDirectory
from types import TracebackType
from typing import Any, Self

from python_on_whales import docker
from python_on_whales.exceptions import DockerException

from botbox.agents.agent import Agent, SessionAgent
from botbox.bind_mounts import Mount, bind_mounts
from botbox.build_lock import build_lock
from botbox.collect import collect
from botbox.lockdown import Lockdown, lockdown
from botbox.RunResult import RunResult
from botbox.Session import Session, read_transcript


class Botbox:
    """An agent, an optional image layer on top of it, and the extra hosts its proxy admits.

    Used as a context manager, it removes every container its runs created on exit.
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
        self.allow = tuple(allow)
        self._containers: list[str] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        containers, self._containers = self._containers, []
        if not containers:
            return
        try:
            docker.container.remove(containers, force=True)
        except DockerException:
            if exc is None:
                raise

    def build(self) -> str:
        """Build the agent's image, then `dockerfile` on top, and return the final tag.

        Built on every call; Docker's layer cache keeps an unchanged build fast. Concurrent
        builds of one tag, from any process, take turns.
        """
        agent = self.agent
        with build_lock(agent.image):
            docker.build(
                agent.dockerfile.parent, tags=agent.image, file=agent.dockerfile, progress=False
            )
        if self.dockerfile is None:
            return agent.image
        digest = hashlib.sha256(str(self.dockerfile).encode()).hexdigest()[:12]
        tag = f"{agent.image.split(':')[0]}-{digest}:latest"
        with build_lock(tag):
            docker.build(self.dockerfile.parent, tags=tag, file=self.dockerfile, progress=False)
        return tag

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

        A returned result leaves its container in place, exited; the caller removes it, or the
        `with` block this box opened does on exit. A run that raises removes its container.
        """
        agent = self.agent
        volumes = bind_mounts(mounts, workdir=workdir, home=agent.home)
        image = self.build()
        with TemporaryDirectory(prefix="botbox-") as scratch:
            home = Path(scratch) / "home"
            home.mkdir()
            agent.stage_auth(home)
            with lockdown((*agent.allow, *self.allow), Path(scratch)) as jail:
                container = docker.run(
                    image,
                    ["sh", "-c", command],
                    detach=True,
                    **self._lockdown_options(home, jail, volumes, workdir),
                )
                self._containers.append(str(container))
                try:
                    stdout, stderr, exit_code = collect(container)
                except BaseException:
                    with suppress(DockerException):
                        docker.container.remove(container, force=True)
                    raise
            transcript = read_transcript(home, agent.transcripts)
        return RunResult(stdout, stderr, exit_code, transcript, jail.log, str(container), image)

    def session(
        self,
        *,
        mounts: Sequence[Mount] = (),
        workdir: str | Path | None = None,
    ) -> Session:
        """Start the agent's CLI in its session mode in the locked-down container and hold it open.

        Same lockdown, home and mounts as `run()`. The container runs under an init process, so
        whatever the agent leaves running in the background is reaped when it exits. Raises
        `TypeError` for an agent with no session mode. The session's container is removed with
        the box's, when its `with` block exits.
        """
        agent = self.agent
        if not isinstance(agent, SessionAgent):
            raise TypeError(f"{type(agent).__name__} has no session mode")
        volumes = bind_mounts(mounts, workdir=workdir, home=agent.home)
        image = self.build()
        resources = ExitStack()
        try:
            scratch = Path(resources.enter_context(TemporaryDirectory(prefix="botbox-")))
            home = scratch / "home"
            home.mkdir()
            agent.stage_auth(home)
            jail = resources.enter_context(lockdown((*agent.allow, *self.allow), scratch))
            container = docker.container.create(
                image,
                ["sh", "-c", agent.session_command()],
                interactive=True,
                init=True,
                **self._lockdown_options(home, jail, volumes, workdir),
            )
            self._containers.append(str(container))
            process = subprocess.Popen(
                ["docker", "start", "--attach", "--interactive", str(container)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except BaseException:
            resources.close()
            raise

        def finish() -> tuple[dict[str, str], str]:
            transcript = read_transcript(home, agent.transcripts)
            resources.close()
            return transcript, jail.log

        return Session(agent, process, str(container), image, finish)

    def _lockdown_options(
        self,
        home: Path,
        jail: Lockdown,
        volumes: list[tuple[str, str, str]],
        workdir: str | Path | None,
    ) -> dict[str, Any]:
        agent = self.agent
        return {
            "envs": jail.envs,
            "volumes": [(str(home), agent.home, "rw"), *volumes],
            "workdir": agent.home if workdir is None else Path(workdir).as_posix(),
            "networks": [jail.network],
            "user": "user",
            "cap_drop": ["ALL"],
            "security_options": ["no-new-privileges"],
        }
