import asyncio
import os
import signal
import threading
from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager, nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import TracebackType
from typing import Any, NamedTuple, Self, cast
from uuid import uuid4

from posix_tools import settle

from adocker import Container, DockerException, Dockerfile, Image, Volume
from adocker import Mount as DockerMount
from botbox.agent_exit import agent_exit
from botbox.agents import Agent, HomeFiles
from botbox.bind_mounts import Mount, bind_mounts
from botbox.build_steps import build_steps
from botbox.check_timeout import check_timeout
from botbox.credential_proxy import Credential, CredentialSource
from botbox.env_labels import env_labels
from botbox.lockdown import HOME_BYTES_ENV, RELAY, SOCKET_DIR, Lockdown, lockdown
from botbox.remove_within import remove_within
from botbox.RunResult import RunResult
from botbox.send_home import send_home
from botbox.Timeout import Timeout
from botbox.warned import warned

STDERR_BYTES = 64 * 1024


class _Setup(NamedTuple):
    limit: float | None
    labels: dict[str, str]
    volumes: list[tuple[str, str, str]]
    source: CredentialSource | None
    credential: Credential | None
    output: Path | None
    home: bytes


class Botbox:
    """An agent, an optional image layer, the extra hosts its proxy admits, and a timeout.

    `timeout` is in seconds and bounds every run; None, the default, is no limit.
    A call's own `timeout` takes its place.
    `memory` caps the agent container in Docker's size format; None leaves it uncapped.
    `pids` caps processes and threads in the agent container; None leaves it uncapped.

    Used as an async context manager, SIGTERM inside the block cancels the task that entered it,
    so a run in progress unwinds and tears down, then the block raises
    `SystemExit(143)`; Python's default SIGTERM exits without unwinding. A SIGTERM handler the
    program set itself is left alone, and so is SIGTERM off the main thread.

    Don't fork while a run is in progress: a forked child shares the loop's state and holds
    the run's pipes.
    """

    def __init__(  # noqa: PLR0913
        self,
        agent: Agent,
        *,
        dockerfile: str | Path | None = None,
        allow: Sequence[str] = (),
        timeout: float | None = None,
        memory: str | None = None,
        pids: int | None = 4096,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        if os.getuid() == 0:
            raise RuntimeError("botbox won't run an agent as root: run it as a regular user")
        self.agent = agent
        self.dockerfile = None if dockerfile is None else Path(dockerfile).resolve()
        if isinstance(allow, str):
            raise TypeError(f"allow takes a sequence of hosts: pass allow=({allow!r},)")
        self.allow = tuple(allow)
        self.timeout = check_timeout(timeout)
        self.memory = memory
        if pids is not None and pids < 1:
            raise ValueError("pids must be at least 1 or None")
        self.pids = pids
        if labels is not None and "botbox.run" in labels:
            raise ValueError("botbox.run is reserved for botbox cleanup")
        self.labels = dict(labels or {})
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
            await Dockerfile(step.file, context=step.context).build(
                step.tag, contexts=step.contexts
            )
        return steps[-1].tag

    async def run(  # noqa: PLR0913
        self,
        command: str,
        *,
        mounts: Sequence[Mount] = (),
        workdir: str | Path | None = None,
        timeout: float | None = None,
        output: str | Path | None = None,
        keep: str | None = None,
    ) -> RunResult:
        """Run `command` as `sh -c` in the locked-down container and return its exit code.

        stdout, stderr and the proxy's output go to stdout.txt, stderr.txt and proxy.log in
        `output` when given, or in the run's temp directory under `TMPDIR` otherwise. With
        `output`, transcripts/ there is mounted over the agent's `sessions_dir`. The three files
        are truncated; other files are kept. A path with `:` raises `ValueError`, since Docker
        can't mount it.

        Mounts, `workdir` and `output` are checked, and the credentials staged, before anything
        is built. The agent's home is in the container, created by the image, and goes with the
        container; the staged credentials are written into it when the container starts. For an
        agent with a `credential_source`, that is a placeholder, and a proxy outside the box sends
        the real credential upstream. A host login that has already expired raises
        `CredentialsExpired` before anything is built. botbox never refreshes it: a run that
        outlives it needs the host's CLI to refresh it, and the new one is sent from the next
        request on. The temp directory is removed when the run ends, so without `output` the
        streams, transcripts and proxy log are not kept; files written to `mounts` are.
        A non-zero exit is a normal result. A daemon that goes away mid-run raises
        `DockerException` with the client's stderr.

        Cancelling the task, or an `asyncio.timeout` firing, removes the run's containers and
        temp directory before the cancel propagates, through any number of further cancels. Both
        containers are labelled `botbox.run=<token>`, and the temp directory is named after the
        token. Raises `DockerException` if setup fails or the
        container never ran to its exit while the daemon was up. A teardown step that fails, or a
        container removal that takes longer than 30 seconds, is a warning, never the error.

        The timeout, `timeout` or else the box's, starts once the image is built. When it runs
        out, the run tears down as a cancel does and raises `Timeout` with `exit_code` -1.
        """
        if keep is not None:
            try:
                await Container(keep).inspect()
            except DockerException:
                pass
            else:
                raise ValueError(f"container {keep} already exists")
        setup = self._setup(mounts=mounts, workdir=workdir, timeout=timeout, output=output)
        return await self._run(command, setup, workdir=workdir, keep=keep, image=await self.build())

    async def restart(  # noqa: PLR0913
        self,
        name: str,
        command: str,
        *,
        mounts: Sequence[Mount] = (),
        workdir: str | Path | None = None,
        timeout: float | None = None,
        output: str | Path | None = None,
    ) -> RunResult:
        """Run on a kept container's filesystem with a fresh proxy and lockdown.

        `output` is handled as in `run`: its log files are truncated. Pass a new `output` to
        keep the earlier run's logs.

        Mounts, `workdir`, `output` and the credentials are checked before the old container is
        touched, so a rejected restart leaves it in place. Committing the container includes its
        home. For agents without a credential source,
        the committed image contains the real staged credential. The image tag is removed after
        the replacement exists; if setup fails before then, the snapshot remains on the daemon.
        """
        previous = Container(name)
        details = await previous.inspect()
        token = details["Config"]["Labels"].get("botbox.run")
        if not token:
            raise ValueError(f"{name} is not a botbox run container")
        setup = self._setup(mounts=mounts, workdir=workdir, timeout=timeout, output=output)
        image = await previous.commit(f"botbox-restart:{uuid4().hex}")
        await previous.remove()
        await Volume(f"botbox-run-{token}").remove()
        try:
            return await self._run(command, setup, workdir=workdir, keep=name, image=image.tag)
        finally:

            async def remove_used_image() -> None:
                try:
                    replacement = await Container(name).inspect()
                except DockerException:
                    return  # The image remains available if replacement setup failed.
                if replacement["Config"]["Image"] == image.tag:
                    await warned(image.remove(), f"remove its restart image {image.tag}")

            await settle(remove_used_image())

    def _setup(
        self,
        *,
        mounts: Sequence[Mount],
        workdir: str | Path | None,
        timeout: float | None,
        output: str | Path | None,
    ) -> _Setup:
        """Check the arguments and stage the credentials and output, before any Docker work."""
        limit = self.timeout if timeout is None else check_timeout(timeout)
        labels = {**env_labels(os.environ), **self.labels}
        volumes = bind_mounts(mounts, workdir=workdir, home=self.agent.home)
        source = self._credential_source()
        credential = None if source is None else source.read()
        prepared = self._prepare_output(output, volumes)
        home = self._home_files()
        return _Setup(limit, labels, volumes, source, credential, prepared, home)

    async def _run(
        self,
        command: str,
        setup: _Setup,
        *,
        workdir: str | Path | None,
        keep: str | None,
        image: str,
    ) -> RunResult:
        agent = self.agent
        limit, labels, volumes, source, credential, output, home = setup
        token = uuid4().hex[:12]
        scratch = TemporaryDirectory(prefix=f"botbox-{token}-")
        deadline = asyncio.timeout(limit)
        try:
            allow = (*agent.allow, *self.allow)
            try:
                async with (
                    deadline,
                    lockdown(
                        allow,
                        Path(scratch.name),
                        token,
                        output,
                        credential=credential,
                        labels=labels,
                    ) as jail,
                    self._following(jail, source, credential),
                ):
                    flags = self._lockdown_flags(token, home, jail, volumes, workdir, labels=labels)
                    try:
                        result = await self._attach(
                            token,
                            image,
                            (RELAY, "sh", "-c", command),
                            home=home,
                            flags=flags,
                            scratch=Path(scratch.name),
                            output=output,
                            keep=keep,
                        )
                    finally:
                        if keep is not None:

                            async def mark_owned_volume() -> None:
                                try:
                                    details = await Container(keep).inspect()
                                except DockerException:
                                    return
                                jail.volume.keep = (
                                    details["Config"]["Labels"].get("botbox.run") == token
                                )

                            await settle(mark_owned_volume())
            except TimeoutError as timed_out:
                if limit is None or not deadline.expired():
                    raise
                raise Timeout(limit, RunResult(-1, container_name=keep)) from timed_out
        finally:
            await settle(warned(asyncio.to_thread(scratch.cleanup), "remove its temp directory"))
        return result

    async def _attach(  # noqa: PLR0913
        self,
        token: str,
        image: str,
        command: Sequence[str],
        *,
        home: bytes,
        flags: dict[str, Any],
        scratch: Path,
        output: Path | None,
        keep: str | None = None,
    ) -> RunResult:
        """Run attached, with `home` on its stdin, then remove the agent container."""
        name = keep if keep is not None else f"botbox-agent-{token}"
        container = Container(name)
        folder = scratch if output is None else output
        try:
            with (
                (folder / "stdout.txt").open("wb") as out,
                (folder / "stderr.txt").open("wb") as err,
            ):
                container = await Image(image).run(
                    *command,
                    name=name,
                    stdin=asyncio.subprocess.PIPE if home else asyncio.subprocess.DEVNULL,
                    stdout=out,
                    stderr=err,
                    **flags,
                )
                if home:
                    stdin = cast("asyncio.StreamWriter", container.stdin)
                    await send_home(stdin, home)
                    stdin.close()
                client = await container.wait()
            result = await agent_exit(container, client, last_stderr(folder / "stderr.txt"))
        finally:
            if keep is None:
                await settle(warned(remove_within(container), f"remove its agent container {name}"))
        return result if keep is None else RunResult(result.exit_code, result.oom_killed, keep)

    def _credential_source(self) -> CredentialSource | None:
        """The agent's credential for the proxy to send, or None to have it copied in."""
        return self.agent.credential_source

    def _following(
        self, jail: Lockdown, source: CredentialSource | None, credential: Credential | None
    ) -> AbstractAsyncContextManager[None]:
        """Follow the host's credential into the proxy while the run lasts, when it has one."""
        if jail.credentials is None or source is None or credential is None:
            return nullcontext()
        return jail.credentials.following(source, credential.secret)

    def _home_files(self) -> bytes:
        """The agent's staged credentials and config, as the archive the relay unpacks."""
        home = HomeFiles()
        self.agent.stage_auth(home)
        return home.archive()

    def _prepare_output(
        self, output: str | Path | None, volumes: list[tuple[str, str, str]]
    ) -> Path | None:
        """Truncate the stream files in `output` and mount its transcripts/ over `sessions_dir`."""
        if output is None:
            return None
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

    def _lockdown_flags(  # noqa: PLR0913
        self,
        token: str,
        home: bytes,
        jail: Lockdown,
        volumes: list[tuple[str, str, str]],
        workdir: str | Path | None,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """`Image.run` options for an agent container, in the proxy's PID namespace, with no
        network.

        No `rm`: the run reads the exit code from the stopped container, then removes it.
        """
        agent = self.agent
        source = self._credential_source()
        injected = {} if jail.credentials is None or source is None else source.env
        return {
            "labels": {**(labels or {}), "botbox.run": token},
            "env": {
                "HOME": agent.home,
                **({HOME_BYTES_ENV: str(len(home))} if home else {}),
                **jail.envs,
                **injected,
            },
            "mounts": [
                jail.volume.mount(SOCKET_DIR, read_only=True),
                *(
                    DockerMount("bind", source, target, mode == "ro")
                    for source, target, mode in volumes
                ),
            ],
            "workdir": agent.home if workdir is None else Path(workdir).as_posix(),
            "network": "none",
            "memory": self.memory,
            "pids_limit": self.pids,
            "pid": f"container:{jail.proxy.name}",
            "user": f"{os.getuid()}:{os.getgid()}",
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges"],
            "log_driver": "none",
        }


def last_stderr(path: Path) -> str:
    """Read the last `STDERR_BYTES` of the run's stderr for an error."""
    with path.open("rb") as stderr:
        stderr.seek(max(0, stderr.seek(0, os.SEEK_END) - STDERR_BYTES))
        return stderr.read().decode(errors="replace")
