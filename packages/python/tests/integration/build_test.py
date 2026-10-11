import contextlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from botbox import Botbox, ClaudeAgent, PiAgent

LAYER = "FROM botbox-claude:latest\nUSER root\nRUN npm install -g vitest@2.1.3\nUSER node\n"


@pytest.fixture
def layer(tmp_path: Path) -> Path:
    directory = tmp_path / "consumer"
    directory.mkdir()
    dockerfile = directory / "Dockerfile"
    dockerfile.write_text(LAYER)
    return dockerfile


@pytest.fixture
def in_layer_directory(layer: Path) -> Iterator[None]:
    with contextlib.chdir(layer.parent):
        yield


def describe_build() -> None:
    def describe_without_a_dockerfile() -> None:
        def it_returns_the_agents_tag() -> None:
            assert Botbox(ClaudeAgent()).build() == "botbox-claude:latest"

        def it_builds_only_the_agents_image(builds: list[dict[str, Any]]) -> None:
            Botbox(ClaudeAgent()).build()
            assert [b["tags"] for b in builds] == ["botbox-claude:latest"]

        def it_builds_the_shipped_claude_dockerfile(builds: list[dict[str, Any]]) -> None:
            Botbox(ClaudeAgent()).build()
            assert builds[0]["file"].name == "claude.Dockerfile"
            assert builds[0]["text"].startswith("FROM node:24.20.0-slim\n")

        def it_uses_the_agent_dockerfiles_directory_as_context(
            builds: list[dict[str, Any]],
        ) -> None:
            Botbox(ClaudeAgent()).build()
            assert builds[0]["context"] == builds[0]["file"].parent

        def it_builds_the_pi_image_for_pi(builds: list[dict[str, Any]]) -> None:
            assert Botbox(PiAgent(provider="openrouter")).build() == "botbox-pi:latest"
            assert builds[0]["file"].name == "pi.Dockerfile"

    def describe_with_a_dockerfile() -> None:
        def it_builds_the_agent_image_then_the_layer(
            builds: list[dict[str, Any]], layer: Path
        ) -> None:
            tag = Botbox(ClaudeAgent(), dockerfile=layer).build()
            assert [b["tags"] for b in builds] == ["botbox-claude:latest", tag]
            assert [b["text"] for b in builds][1] == LAYER

        def it_returns_a_tag_other_than_the_agents(layer: Path) -> None:
            assert Botbox(ClaudeAgent(), dockerfile=layer).build() != "botbox-claude:latest"

        def it_uses_the_dockerfiles_directory_as_context(
            builds: list[dict[str, Any]], layer: Path
        ) -> None:
            Botbox(ClaudeAgent(), dockerfile=layer).build()
            assert builds[1]["context"] == layer.parent
            assert builds[1]["file"] == layer

        def it_accepts_the_dockerfile_as_a_string(
            builds: list[dict[str, Any]], layer: Path
        ) -> None:
            Botbox(ClaudeAgent(), dockerfile=str(layer)).build()
            assert builds[1]["file"] == layer

        @pytest.mark.usefixtures("in_layer_directory")
        def it_resolves_a_relative_dockerfile_against_the_working_directory(
            builds: list[dict[str, Any]], layer: Path
        ) -> None:
            Botbox(ClaudeAgent(), dockerfile="./Dockerfile").build()
            assert builds[1]["context"] == layer.parent
            assert builds[1]["file"] == layer

        def it_returns_the_same_tag_each_call(layer: Path) -> None:
            box = Botbox(ClaudeAgent(), dockerfile=layer)
            assert box.build() == box.build()

        def it_tags_different_dockerfiles_differently(layer: Path, tmp_path: Path) -> None:
            other = tmp_path / "other" / "Dockerfile"
            other.parent.mkdir()
            other.write_text(LAYER)
            assert (
                Botbox(ClaudeAgent(), dockerfile=layer).build()
                != Botbox(ClaudeAgent(), dockerfile=other).build()
            )

        def it_raises_when_the_layer_fails_to_build(docker_build: MagicMock, layer: Path) -> None:
            docker_build.side_effect = [None, RuntimeError("layer failed")]
            with pytest.raises(RuntimeError, match="layer failed"):
                Botbox(ClaudeAgent(), dockerfile=layer).build()

    def it_builds_every_call(builds: list[dict[str, Any]]) -> None:
        box = Botbox(ClaudeAgent())
        box.build()
        box.build()
        assert [b["tags"] for b in builds] == ["botbox-claude:latest", "botbox-claude:latest"]

    def it_skips_the_layer_when_the_agent_image_fails(docker_build: MagicMock, layer: Path) -> None:
        docker_build.side_effect = RuntimeError("agent failed")
        with pytest.raises(RuntimeError, match="agent failed"):
            Botbox(ClaudeAgent(), dockerfile=layer).build()
        assert docker_build.call_count == 1


def describe_botbox() -> None:
    def it_takes_its_options_by_keyword_only(layer: Path) -> None:
        with pytest.raises(TypeError):
            Botbox(ClaudeAgent(), layer)  # type: ignore[misc]

    def it_does_not_build_on_construction(docker_build: MagicMock, layer: Path) -> None:
        Botbox(ClaudeAgent(), dockerfile=layer, allow=["registry.npmjs.org"])
        docker_build.assert_not_called()
