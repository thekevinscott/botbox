import hashlib
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory
from types import TracebackType
from typing import Self

from python_on_whales import docker
from python_on_whales.exceptions import DockerException

from botbox.agents.agent import Agent
from botbox.bind_mounts import Mount, bind_mounts
from botbox.build_lock import build_lock
from botbox.collect import collect
from botbox.lockdown import lockdown
from botbox.RunResult import RunResult


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
                    envs=jail.envs,
                    volumes=[(str(home), agent.home, "rw"), *volumes],
                    workdir=agent.home if workdir is None else Path(workdir).as_posix(),
                    networks=[jail.network],
                    user="node",
                    cap_drop=["ALL"],
                    security_options=["no-new-privileges"],
                )
                self._containers.append(str(container))
                try:
                    stdout, stderr, exit_code = collect(container)
                except BaseException:
                    with suppress(DockerException):
                        docker.container.remove(container, force=True)
                    raise
            transcript = {
                path.relative_to(home).as_posix(): path.read_text()
                for path in sorted(home.glob(agent.transcripts))
                if path.is_file()
            }
        return RunResult(stdout, stderr, exit_code, transcript, jail.log, str(container), image)
