"""The shipped pi wrapper drops tool progress in a real container."""

import asyncio
import json
import shlex
from pathlib import Path

import pytest

from botbox import Botbox, PiAgent

INTEGRATION = Path(__file__).parents[1] / "integration"
TOOL = json.dumps({"command": "for n in 1 2 3 4 5 6 7 8; do echo chunk-$n; sleep 0.2; done"})


@pytest.fixture(scope="module")
def outputs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, int]:
    root = tmp_path_factory.mktemp("pi-stdout-filter")
    box = Botbox(PiAgent("openrouter", api_key="unused"), timeout=60)
    command = shlex.join(["python3", "/fake/fake_model_test.py", TOOL])
    control, filtered, failed = (root / name for name in ("control", "filtered", "failed"))
    control_run = asyncio.run(
        box.run(
            f"PI_EXECUTABLE=/usr/local/bin/pi-unfiltered {command}",
            mounts=[(INTEGRATION, "/fake", "ro")],
            output=control,
        )
    )
    filtered_run = asyncio.run(
        box.run(command, mounts=[(INTEGRATION, "/fake", "ro")], output=filtered)
    )
    failure = asyncio.run(box.run("pi --mode bogus -p hi", output=failed))
    assert control_run.exit_code == filtered_run.exit_code == 0
    return control, filtered, failure.exit_code


def describe_pi_stdout_filter() -> None:
    def it_drops_progress_events_that_the_unfiltered_pi_emits(
        outputs: tuple[Path, Path, int],
    ) -> None:
        control, filtered, _ = outputs
        before = (control / "stdout.txt").read_text()
        after = (filtered / "stdout.txt").read_text()
        assert '"type":"tool_execution_update"' in before
        assert '"type":"tool_execution_update"' not in after
        assert '"type":"tool_execution_end"' in after

    def it_preserves_pi_exit_code(outputs: tuple[Path, Path, int]) -> None:
        assert outputs[2] == 1
