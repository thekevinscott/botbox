"""The Pi image's tool-timeout extension, run by a real pi against a fake model, offline."""

import asyncio
import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from adocker import Container, Image, Mount
from botbox import Botbox, PiAgent

FAKE_MODEL = Path(__file__).with_name("fake_model_test.py")
EXTENSION = "/usr/local/lib/botbox/tool-timeout.ts"


@pytest.fixture(scope="module")
def image() -> str:
    return asyncio.run(Botbox(PiAgent("openrouter", api_key="unused")).build())


async def bash_call(image: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], float]:
    """pi's `tool_execution_end` for the one bash call, and how long the run took."""
    out, err = bytearray(), bytearray()
    name = f"botbox-test-{uuid4().hex[:12]}"
    started = time.monotonic()
    try:
        container = await Image(image).run(
            *("/fake/model.py", json.dumps(arguments), "-e", EXTENSION),
            name=name,
            stdin=None,
            stdout=out.extend,
            stderr=err.extend,
            network="none",
            env={"BOTBOX_TOOL_TIMEOUT": "2"},
            mounts=[Mount("bind", str(FAKE_MODEL), "/fake/model.py", read_only=True)],
            entrypoint="python3",
        )
        code = await container.wait()
    finally:
        await Container(name).remove()
    elapsed = time.monotonic() - started
    assert code == 0, err.decode()
    events = [json.loads(line) for line in out.decode().splitlines() if line.startswith("{")]
    [end] = [event for event in events if event["type"] == "tool_execution_end"]
    return end, elapsed


def describe_the_tool_timeout_extension() -> None:
    @pytest.mark.parametrize(
        "arguments",
        [
            {"command": "sleep 30; echo finished"},
            {"command": "sleep 30; echo finished", "timeout": 600},
        ],
        ids=["no timeout asked", "a longer timeout asked"],
    )
    async def it_stops_a_bash_call_at_the_limit(image: str, arguments: dict[str, Any]) -> None:
        end, elapsed = await bash_call(image, arguments)
        assert end["result"]["content"] == [
            {"type": "text", "text": "Command timed out after 2 seconds"}
        ]
        assert end["isError"] is True
        assert elapsed < 15
