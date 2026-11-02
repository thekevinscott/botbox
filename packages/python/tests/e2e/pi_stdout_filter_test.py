"""The shipped pi wrapper drops tool progress in a real container."""

import asyncio
from pathlib import Path

import pytest
from conftest import OPENROUTER_API_KEY

from botbox import Botbox, PiAgent

PROMPT = (
    "Run this exact bash command: "
    "`for n in 1 2 3 4 5 6 7 8; do echo chunk-$n; sleep 0.2; done`. "
    "Then reply with what the tool returned."
)


@pytest.fixture(scope="module")
def outputs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, int]:
    root = tmp_path_factory.mktemp("pi-stdout-filter")
    agent = PiAgent("openrouter", "openai/gpt-4o-mini", api_key=OPENROUTER_API_KEY)
    box = Botbox(agent, timeout=60)
    command = agent.command(PROMPT)
    control, filtered, failed = (root / name for name in ("control", "filtered", "failed"))
    control_run = asyncio.run(
        box.run(
            command.replace("pi -p ", "pi-unfiltered -p ", 1),
            output=control,
        )
    )
    filtered_run = asyncio.run(box.run(command, output=filtered))
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
