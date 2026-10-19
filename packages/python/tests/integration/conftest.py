"""Integration tests: Docker mocked at the python_on_whales boundary."""

from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from python_on_whales.exceptions import DockerException


@pytest.fixture
def builds() -> list[dict[str, Any]]:
    """Every `docker build` in order: context, tag, Dockerfile, and the Dockerfile's text."""
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
                }
            )

        build.side_effect = record
        yield build


class Daemon:
    """The Docker daemon as `run()` sees it: what it was asked to run, and how the run goes.

    `container` stands in for the agent's process: it gets the staged home and the proxy's
    log directory as host paths, and writes into them the way the CLI and tinyproxy would.
    """

    def __init__(self) -> None:
        self.runs: list[dict[str, Any]] = []
        self.logs: list[tuple[str, bytes]] = []
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
        patch("python_on_whales.docker.logs", autospec=True) as logs,
        patch("python_on_whales.docker.wait", autospec=True) as wait,
        patch("python_on_whales.docker.network", autospec=True) as network,
        patch("python_on_whales.docker.container", autospec=True) as container,
        patch("python_on_whales.utils.run", autospec=True) as cli,
    ):
        network.docker_cmd = ["docker"]

        def record_run(image: str, command: Sequence[str] = (), **options: Any) -> str:
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
            if image == PROXY_IMAGE:
                return "proxy-container"
            home = next(Path(s) for s, t, _ in volumes if t == "/home/user")
            proxy_log = next(
                Path(s) for s, t, _ in daemon.proxy["volumes"] if t == "/var/log/tinyproxy"
            )
            daemon.container(home, proxy_log / "tinyproxy.log")
            return "agent-container"

        def stream(_container: str, **_options: Any) -> Iterator[tuple[str, bytes]]:
            yield from daemon.logs
            if daemon.dies_mid_run:
                raise DockerException(["docker", "container", "logs"], 1, stderr=b"EOF")

        def exit_code(_container: str) -> int:
            if daemon.dies_mid_run:
                raise DockerException(["docker", "container", "wait"], 1, stderr=b"EOF")
            return daemon.exit_code

        run.side_effect = record_run
        logs.side_effect = stream
        wait.side_effect = exit_code
        yield {
            "run": run,
            "logs": logs,
            "wait": wait,
            "network": network,
            "container": container,
            "cli": cli,
        }
