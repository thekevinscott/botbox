"""Concurrent builds of the same tag, from separate processes, as parallel `run()`s do."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest
from python_on_whales.exceptions import DockerException

from botbox import Botbox, ClaudeAgent

PROCESSES = 4


@pytest.fixture
def layer(tmp_path: Path) -> Path:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM botbox-claude:latest\nRUN echo layer > /tmp/layer\n")
    return dockerfile


def build(box: Botbox) -> str:
    """The tag, or the error's stderr: DockerException does not survive the trip back."""
    try:
        return box.build()
    except DockerException as error:
        return str(error.stderr).strip()


def build_concurrently(box: Botbox) -> list[str]:
    with ProcessPoolExecutor(PROCESSES) as pool:
        return list(pool.map(build, [box] * PROCESSES))


def describe_concurrent_builds() -> None:
    @pytest.mark.usefixtures("box")
    def it_returns_the_agents_tag_to_every_caller() -> None:
        assert build_concurrently(Botbox(ClaudeAgent())) == ["botbox-claude:latest"] * PROCESSES

    @pytest.mark.usefixtures("box")
    def it_returns_the_layers_tag_to_every_caller(layer: Path) -> None:
        box = Botbox(ClaudeAgent(), dockerfile=layer)
        assert build_concurrently(box) == [box.build()] * PROCESSES
