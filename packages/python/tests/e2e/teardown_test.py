"""What a real run leaves behind on the host: its exited container, pass or fail."""

import subprocess

import pytest
from conftest import leftovers

from botbox import Botbox


def describe_teardown() -> None:
    @pytest.mark.parametrize("command", ["true", "exit 1", "kill -9 $$"])
    def it_leaves_only_its_container(box: Botbox, command: str) -> None:
        before = leftovers()
        result = box.run(command)
        try:
            name = subprocess.run(
                ["docker", "container", "inspect", "--format", "{{.Name}}", result.container],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            assert leftovers() - before == {f"container {name.lstrip('/')}"}
        finally:
            subprocess.run(["docker", "rm", "-f", result.container], check=True)
        assert leftovers() == before
