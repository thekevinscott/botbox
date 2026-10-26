"""`Botbox.build()` against a fake `docker` on PATH that records each build."""

import contextlib
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import botbox
from botbox import Botbox, ClaudeAgent, CodexAgent, DockerException, PiAgent

# Logs its build, then fails or succeeds as BUILDX_PLAN says for the tag.
FAKE_DOCKER = """
import json, os, sys
argv = sys.argv[1:]
option = lambda name: argv[argv.index(name) + 1]
build = {
    "argv": argv,
    "text": open(option("--file")).read(),
    "contexts": dict(
        argv[i + 1].split("=", 1) for i, arg in enumerate(argv) if arg == "--build-context"
    ),
}
with open(os.environ["BUILDX_LOG"], "a") as log:
    log.write(json.dumps(build) + "\\n")
plan = json.load(open(os.environ["BUILDX_PLAN"])).get(option("--tag"), {})
if "fail" in plan:
    sys.stderr.write(plan["fail"])
    sys.exit(1)
"""


class Buildx:
    """The builds the fake `docker` was asked for, and what it does for each tag."""

    def __init__(self, directory: Path) -> None:
        self.log = directory / "builds.jsonl"
        self.plan_file = directory / "plan.json"
        self.plan: dict[str, dict[str, Any]] = {}
        self.plan_file.write_text("{}")

    def fail(self, tag: str, stderr: str) -> None:
        self.plan[tag] = {"fail": stderr}
        self.plan_file.write_text(json.dumps(self.plan))

    @property
    def builds(self) -> list[dict[str, Any]]:
        if not self.log.exists():
            return []
        builds = []
        for line in self.log.read_text().splitlines():
            build = json.loads(line)
            argv = build["argv"]
            builds.append(
                {
                    **build,
                    "load": "--load" in argv,
                    "progress": next(
                        (a.split("=", 1)[1] for a in argv if a.startswith("--progress=")), None
                    ),
                    "tag": argv[argv.index("--tag") + 1],
                    "file": Path(argv[argv.index("--file") + 1]),
                    "context": Path(argv[-1]),
                }
            )
        return builds


@pytest.fixture(autouse=True)
def buildx(tmp_path: Path) -> Iterator[Buildx]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    fake.write_text(f"#!{sys.executable}\n{FAKE_DOCKER}")
    fake.chmod(0o755)
    recorder = Buildx(tmp_path)
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "BUILDX_LOG": str(recorder.log),
        "BUILDX_PLAN": str(recorder.plan_file),
    }
    with patch.dict(os.environ, env):
        yield recorder


LAYER = "FROM botbox-claude:latest\nUSER root\nRUN npm install -g vitest@2.1.3\nUSER user\n"
RELAY_DIR = Path(botbox.__file__).with_name("relay")


@pytest.fixture
def layer(tmp_path: Path) -> Path:
    directory = tmp_path / "consumer"
    directory.mkdir()
    dockerfile = directory / "Dockerfile"
    dockerfile.write_text(LAYER)
    return dockerfile


def describe_build() -> None:
    def describe_without_a_dockerfile() -> None:
        async def it_returns_the_agents_tag() -> None:
            assert await Botbox(ClaudeAgent()).build() == "botbox-claude:latest"

        async def it_builds_the_shipped_claude_dockerfile_with_buildx(buildx: Buildx) -> None:
            await Botbox(ClaudeAgent()).build()
            [build] = buildx.builds
            assert build["tag"] == "botbox-claude:latest"
            assert build["file"].parts[-2:] == ("claude", "Dockerfile")
            assert build["text"].startswith("FROM node:24.20.0-slim\n")
            assert build["context"] == build["file"].parent

        async def it_loads_the_image_quietly(buildx: Buildx) -> None:
            await Botbox(ClaudeAgent()).build()
            assert buildx.builds[0]["load"]
            assert buildx.builds[0]["progress"] == "quiet"

        async def it_names_the_relay_as_the_botbox_build_context(buildx: Buildx) -> None:
            await Botbox(ClaudeAgent()).build()
            assert buildx.builds[0]["contexts"] == {"botbox": str(RELAY_DIR)}

        async def it_builds_the_pi_image_for_pi(buildx: Buildx) -> None:
            assert await Botbox(PiAgent(provider="openrouter")).build() == "botbox-pi:latest"
            assert buildx.builds[0]["file"].parts[-2:] == ("pi", "Dockerfile")

        async def it_builds_the_codex_image_for_codex(buildx: Buildx) -> None:
            assert await Botbox(CodexAgent()).build() == "botbox-codex:latest"
            assert buildx.builds[0]["file"].parts[-2:] == ("codex", "Dockerfile")

    def describe_with_a_dockerfile() -> None:
        async def it_builds_the_agent_image_then_the_layer(buildx: Buildx, layer: Path) -> None:
            tag = await Botbox(ClaudeAgent(), dockerfile=layer).build()
            assert [b["tag"] for b in buildx.builds] == ["botbox-claude:latest", tag]
            assert buildx.builds[1]["text"] == LAYER
            assert buildx.builds[1]["context"] == layer.parent
            assert buildx.builds[1]["contexts"] == {}

        async def it_returns_a_tag_other_than_the_agents(layer: Path) -> None:
            assert await Botbox(ClaudeAgent(), dockerfile=layer).build() != "botbox-claude:latest"

        async def it_builds_the_dockerfile_it_was_given(buildx: Buildx, layer: Path) -> None:
            await Botbox(ClaudeAgent(), dockerfile=layer).build()
            assert buildx.builds[1]["file"] == layer

        async def it_accepts_the_dockerfile_as_a_string(buildx: Buildx, layer: Path) -> None:
            await Botbox(ClaudeAgent(), dockerfile=str(layer)).build()
            assert buildx.builds[1]["file"] == layer

        async def it_resolves_a_relative_dockerfile_against_the_working_directory(
            buildx: Buildx, layer: Path
        ) -> None:
            with contextlib.chdir(layer.parent):
                await Botbox(ClaudeAgent(), dockerfile="./Dockerfile").build()
            assert buildx.builds[1]["context"] == layer.parent
            assert buildx.builds[1]["file"] == layer

        async def it_returns_the_same_tag_each_call(layer: Path) -> None:
            box = Botbox(ClaudeAgent(), dockerfile=layer)
            assert await box.build() == await box.build()

        async def it_tags_different_dockerfiles_differently(layer: Path, tmp_path: Path) -> None:
            other = tmp_path / "other" / "Dockerfile"
            other.parent.mkdir()
            other.write_text(LAYER)
            assert (
                await Botbox(ClaudeAgent(), dockerfile=layer).build()
                != await Botbox(ClaudeAgent(), dockerfile=other).build()
            )

        async def it_raises_with_the_builds_error_when_the_layer_fails(
            buildx: Buildx, layer: Path
        ) -> None:
            buildx.fail(
                await Botbox(ClaudeAgent(), dockerfile=layer).build(),
                "ERROR: failed to solve: npm ERR!\n",
            )
            with pytest.raises(DockerException) as error:
                await Botbox(ClaudeAgent(), dockerfile=layer).build()
            assert error.value.return_code == 1
            assert error.value.stderr == "ERROR: failed to solve: npm ERR!\n"

    async def it_skips_the_layer_when_the_agent_image_fails(buildx: Buildx, layer: Path) -> None:
        buildx.fail("botbox-claude:latest", "ERROR: failed to solve\n")
        with pytest.raises(DockerException):
            await Botbox(ClaudeAgent(), dockerfile=layer).build()
        assert len(buildx.builds) == 1

    async def it_builds_every_call(buildx: Buildx) -> None:
        box = Botbox(ClaudeAgent())
        await box.build()
        await box.build()
        assert [b["tag"] for b in buildx.builds] == ["botbox-claude:latest"] * 2


def describe_botbox() -> None:
    def it_takes_its_options_by_keyword_only(layer: Path) -> None:
        with pytest.raises(TypeError):
            Botbox(ClaudeAgent(), layer)  # type: ignore[call-arg]

    def it_does_not_build_on_construction(buildx: Buildx, layer: Path) -> None:
        Botbox(ClaudeAgent(), dockerfile=layer, allow=["registry.npmjs.org"])
        assert buildx.builds == []
