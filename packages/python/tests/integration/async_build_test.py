from pathlib import Path
from typing import Any

import pytest

import botbox
from botbox import AsyncBotbox, Botbox, ClaudeAgent, CodexAgent, DockerException, PiAgent

Buildx = Any

LAYER = "FROM botbox-claude:latest\nUSER root\nRUN npm install -g vitest@2.1.3\nUSER user\n"
RELAY_DIR = Path(botbox.__file__).with_name("relay")


@pytest.fixture
def layer(tmp_path: Path) -> Path:
    directory = tmp_path / "consumer"
    directory.mkdir()
    dockerfile = directory / "Dockerfile"
    dockerfile.write_text(LAYER)
    return dockerfile


def describe_async_build() -> None:
    def describe_without_a_dockerfile() -> None:
        async def it_returns_the_agents_tag() -> None:
            assert await AsyncBotbox(ClaudeAgent()).build() == "botbox-claude:latest"

        async def it_builds_the_shipped_claude_dockerfile_with_buildx(buildx: Buildx) -> None:
            await AsyncBotbox(ClaudeAgent()).build()
            [build] = buildx.builds
            assert build["tag"] == "botbox-claude:latest"
            assert build["file"].parts[-2:] == ("claude", "Dockerfile")
            assert build["text"].startswith("FROM node:24.20.0-slim\n")
            assert build["context"] == build["file"].parent

        async def it_loads_the_image_quietly(buildx: Buildx) -> None:
            await AsyncBotbox(ClaudeAgent()).build()
            assert buildx.builds[0]["load"]
            assert buildx.builds[0]["progress"] == "quiet"

        async def it_names_the_relay_as_the_botbox_build_context(buildx: Buildx) -> None:
            await AsyncBotbox(ClaudeAgent()).build()
            assert buildx.builds[0]["contexts"] == {"botbox": str(RELAY_DIR)}

        async def it_builds_the_pi_image_for_pi(buildx: Buildx) -> None:
            assert await AsyncBotbox(PiAgent(provider="openrouter")).build() == "botbox-pi:latest"
            assert buildx.builds[0]["file"].parts[-2:] == ("pi", "Dockerfile")

        async def it_builds_the_codex_image_for_codex(buildx: Buildx) -> None:
            assert await AsyncBotbox(CodexAgent()).build() == "botbox-codex:latest"
            assert buildx.builds[0]["file"].parts[-2:] == ("codex", "Dockerfile")

    def describe_with_a_dockerfile() -> None:
        async def it_builds_the_agent_image_then_the_layer(buildx: Buildx, layer: Path) -> None:
            tag = await AsyncBotbox(ClaudeAgent(), dockerfile=layer).build()
            assert [b["tag"] for b in buildx.builds] == ["botbox-claude:latest", tag]
            assert buildx.builds[1]["text"] == LAYER
            assert buildx.builds[1]["context"] == layer.parent
            assert buildx.builds[1]["contexts"] == {}

        async def it_tags_the_layer_as_the_sync_build_does(layer: Path) -> None:
            tag = await AsyncBotbox(ClaudeAgent(), dockerfile=layer).build()
            assert tag == Botbox(ClaudeAgent(), dockerfile=layer).build()

        async def it_raises_with_the_builds_error_when_the_layer_fails(
            buildx: Buildx, layer: Path
        ) -> None:
            buildx.fails[Botbox(ClaudeAgent(), dockerfile=layer).build()] = (
                b"ERROR: failed to solve: npm ERR!\n"
            )
            with pytest.raises(DockerException) as error:
                await AsyncBotbox(ClaudeAgent(), dockerfile=layer).build()
            assert error.value.return_code == 1
            assert error.value.stderr == "ERROR: failed to solve: npm ERR!\n"

    async def it_skips_the_layer_when_the_agent_image_fails(buildx: Buildx, layer: Path) -> None:
        buildx.fails["botbox-claude:latest"] = b"ERROR: failed to solve\n"
        with pytest.raises(DockerException):
            await AsyncBotbox(ClaudeAgent(), dockerfile=layer).build()
        assert len(buildx.builds) == 1

    async def it_builds_every_call(buildx: Buildx) -> None:
        box = AsyncBotbox(ClaudeAgent())
        await box.build()
        await box.build()
        assert [b["tag"] for b in buildx.builds] == ["botbox-claude:latest"] * 2
