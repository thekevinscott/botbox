from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from adocker.Dockerfile import Dockerfile


@pytest.fixture
def run_docker() -> Iterator[AsyncMock]:
    with patch("adocker.Dockerfile.run_docker", autospec=True) as m:
        yield m


def describe_Dockerfile() -> None:
    def it_builds_in_its_own_folder_unless_given_a_context() -> None:
        assert Dockerfile("/a/b/Dockerfile").context == Path("/a/b")
        assert Dockerfile("/a/b/Dockerfile", context="/c").context == Path("/c")

    async def it_builds_with_buildx_and_returns_the_image(run_docker: AsyncMock) -> None:
        image = await Dockerfile(Path("/a/D"), context=Path("/c")).build(
            "x:latest", contexts={"b": "/r", "e": Path("/s")}
        )
        assert image.tag == "x:latest"
        run_docker.assert_awaited_once_with(
            "buildx",
            "build",
            "--load",
            "--progress=quiet",
            "--tag",
            "x:latest",
            "--file",
            "/a/D",
            "--build-context",
            "b=/r",
            "--build-context",
            "e=/s",
            "/c",
        )

    async def it_builds_with_no_named_contexts_by_default(run_docker: AsyncMock) -> None:
        await Dockerfile("/a/D").build("x:latest")
        assert "--build-context" not in run_docker.await_args_list[0].args

    async def it_raises_what_the_build_raised(run_docker: AsyncMock) -> None:
        run_docker.side_effect = RuntimeError("failed to solve")
        with pytest.raises(RuntimeError, match="failed to solve"):
            await Dockerfile("/a/D").build("x:latest")

    def it_takes_its_context_by_keyword_only() -> None:
        with pytest.raises(TypeError):
            Dockerfile("/a/D", "/c")  # type: ignore[call-arg]
