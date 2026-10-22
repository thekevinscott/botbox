"""Integration tests: Docker mocked at the python_on_whales boundary."""

import argparse
import io
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from python_on_whales.exceptions import DockerException


@pytest.fixture
def builds() -> list[dict[str, Any]]:
    """Every `docker build` in order: context, tag, Dockerfile, its text, and named contexts."""
    return []


@pytest.fixture(autouse=True)
def docker_build(builds: list[dict[str, Any]]) -> Iterator[MagicMock]:
    with patch("python_on_whales.docker.build", autospec=True) as build:

        def record(context: Path, **options: Any) -> None:
            builds.append(
                {
                    "context": Path(context),
                    "tags": options["tags"],
                    "file": Path(options["file"]),
                    "text": Path(options["file"]).read_text(),
                    "contexts": options.get("build_contexts", {}),
                }
            )

        build.side_effect = record
        yield build


class Daemon:
    """The Docker daemon as `run()` sees it: what it was asked to run, and how the run goes.

    `container` stands in for the agent's process: it gets the staged home and the proxy's
    log directory as host paths, and writes into them the way the CLI and tinyproxy would.
    Both containers run attached, through `docker run`; `attached` holds each such command.
    `dies_mid_run` cuts the agent's client the way a lost daemon does: exit 125 and
    `docker version` failing.
    """

    def __init__(self) -> None:
        self.runs: list[dict[str, Any]] = []
        self.attached: list[list[str]] = []
        self.stdout = b""
        self.stderr = b""
        self.exit_code = 0
        self.dies_mid_run = False
        self.container: Callable[[Path, Path], None] = lambda _home, _proxy_log: None

    @property
    def proxy(self) -> dict[str, Any]:
        """The latest run's proxy sidecar."""
        return [r for r in self.runs if r["image"] == PROXY_IMAGE][-1]

    @property
    def agent(self) -> dict[str, Any]:
        """The latest run's agent container."""
        return [r for r in self.runs if r["image"] != PROXY_IMAGE][-1]


PROXY_IMAGE = "botbox-proxy:latest"

# `docker run` flags, parsed back into python_on_whales' option names.
RUN = argparse.ArgumentParser()
RUN.add_argument("--interactive", action="store_true")
RUN.add_argument("--rm", dest="remove", action="store_true")
RUN.add_argument("--init", action="store_true")
RUN.add_argument("--name")
RUN.add_argument("--user")
RUN.add_argument("--workdir")
RUN.add_argument("--pid")
RUN.add_argument("--pids-limit", type=int)
RUN.add_argument("--env", dest="envs", action="append", default=[])
RUN.add_argument("--network", dest="networks", action="append", default=[])
RUN.add_argument("--cap-drop", action="append", default=[])
RUN.add_argument("--security-opt", dest="security_options", action="append", default=[])
RUN.add_argument("--volume", dest="volumes", action="append", default=[])
RUN.add_argument("image")
RUN.add_argument("command", nargs=argparse.REMAINDER)


def parse_run(argv: list[str]) -> dict[str, Any]:
    assert argv[:2] == ["docker", "run"]
    options = vars(RUN.parse_args(argv[2:]))
    options["envs"] = dict(e.split("=", 1) for e in options["envs"])
    options["volumes"] = [tuple(v.split(":")) for v in options["volumes"]]
    return options


def snapshot(source: str) -> dict[str, str]:
    root = Path(source)
    if root.is_file():
        return {".": root.read_text()}
    files = sorted(p for p in root.rglob("*") if p.is_file())
    return {p.relative_to(root).as_posix(): p.read_text() for p in files}


@pytest.fixture
def daemon() -> Daemon:
    return Daemon()


@pytest.fixture(autouse=True)
def docker(daemon: Daemon) -> Iterator[dict[str, MagicMock]]:
    """Every daemon-facing call `run()` makes, patched where python_on_whales defines it."""
    with (
        patch("python_on_whales.docker.run", autospec=True) as run,
        patch("python_on_whales.docker.version", autospec=True) as version,
        patch("python_on_whales.docker.network", autospec=True) as network,
        patch("python_on_whales.docker.container", autospec=True) as container,
        patch("python_on_whales.utils.run", autospec=True) as cli,
        patch("subprocess.Popen", autospec=True) as popen,
    ):

        def record(image: str, command: Sequence[str] = (), **options: Any) -> None:
            volumes = [(str(s), str(t), m) for s, t, m in options.get("volumes", ())]
            daemon.runs.append(
                {
                    "image": image,
                    "command": list(command),
                    **options,
                    "volumes": volumes,
                    "files": {target: snapshot(source) for source, target, _ in volumes},
                    "modes": {target: Path(source).stat().st_mode for source, target, _ in volumes},
                }
            )

        def start_proxy() -> MagicMock:
            """The proxy comes up: its socket appears in the directory it was given."""
            sockets = next(s for s, t, _ in daemon.proxy["volumes"] if t == "/run/botbox")
            (Path(sockets) / "proxy.sock").touch()
            process = MagicMock()
            process.poll.return_value = None
            process.wait.return_value = 0
            return process

        def start_agent() -> MagicMock:
            """The agent runs to its exit while attached: home and proxy log written, output out."""
            home = next(Path(s) for s, t, _ in daemon.agent["volumes"] if t == "/home/user")
            proxy_log = next(
                Path(s) for s, t, _ in daemon.proxy["volumes"] if t == "/var/log/tinyproxy"
            )
            daemon.container(home, proxy_log / "tinyproxy.log")
            process = MagicMock()
            process.stdout = io.BytesIO(daemon.stdout)
            process.stderr = io.BytesIO(daemon.stderr)
            process.wait.return_value = 125 if daemon.dies_mid_run else daemon.exit_code
            return process

        def start(argv: list[str], **_options: Any) -> MagicMock:
            daemon.attached.append(argv)
            record(**parse_run(argv))
            return start_proxy() if daemon.runs[-1]["image"] == PROXY_IMAGE else start_agent()

        def answer() -> None:
            if daemon.dies_mid_run:
                raise DockerException(["docker", "version"], 1, stderr=b"Cannot connect")

        popen.side_effect = start
        version.side_effect = answer
        yield {
            "run": run,
            "version": version,
            "network": network,
            "container": container,
            "cli": cli,
            "popen": popen,
        }
