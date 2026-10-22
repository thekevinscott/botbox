from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from botbox.docker.build import build


@pytest.fixture
def run_docker() -> Iterator[AsyncMock]:
    with patch("botbox.docker.build.run_docker", autospec=True) as m:
        yield m


def describe_build() -> None:
    async def it_takes_its_options_by_keyword_only(run_docker: AsyncMock) -> None:
        with pytest.raises(TypeError):
            await build(Path("/ctx"), "a:latest", Path("/ctx/D"))  # type: ignore[misc]

    async def it_loads_a_quiet_buildx_build_of_the_context(run_docker: AsyncMock) -> None:
        await build(Path("/ctx"), tag="a:latest", file=Path("/ctx/Dockerfile"))
        run_docker.assert_awaited_once_with(
            "buildx",
            "build",
            "--load",
            "--progress=quiet",
            "--tag",
            "a:latest",
            "--file",
            "/ctx/Dockerfile",
            "/ctx",
        )

    async def it_passes_each_named_context(run_docker: AsyncMock) -> None:
        await build(
            Path("/ctx"),
            tag="a:latest",
            file=Path("/ctx/D"),
            contexts={"botbox": Path("/relay"), "base": "docker-image://busybox"},
        )
        assert run_docker.await_args_list[0].args[6:] == (
            "--file",
            "/ctx/D",
            "--build-context",
            "botbox=/relay",
            "--build-context",
            "base=docker-image://busybox",
            "/ctx",
        )
