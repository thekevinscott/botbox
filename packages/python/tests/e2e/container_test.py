"""The container a completed run leaves behind: exited, inspectable, the caller's to remove."""

import json
import subprocess
from collections.abc import Iterator

import pytest
from conftest import removed

from botbox import Botbox, RunResult


@pytest.fixture(scope="module")
def result(box: Botbox) -> Iterator[RunResult]:
    yield from removed(box.run("echo hi > /tmp/mark"))


def inspect(container: str) -> dict:
    out = subprocess.run(
        ["docker", "container", "inspect", container], check=True, capture_output=True, text=True
    ).stdout
    return json.loads(out)[0]


def describe_the_kept_container() -> None:
    def it_is_still_there_and_exited(result: RunResult) -> None:
        assert inspect(result.container)["State"]["Status"] == "exited"

    def it_holds_what_the_command_wrote_outside_the_mounts(result: RunResult) -> None:
        diff = subprocess.run(
            ["docker", "diff", result.container], check=True, capture_output=True, text=True
        ).stdout
        assert "A /tmp/mark" in diff.splitlines()

    def it_names_the_image_that_ran(box: Botbox, result: RunResult) -> None:
        assert result.image == box.build()
        assert inspect(result.container)["Config"]["Image"] == result.image
