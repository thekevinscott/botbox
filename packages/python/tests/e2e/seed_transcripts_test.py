"""A pi run seeded with an earlier run's transcripts sees its sessions and keeps them."""

import asyncio
import json
from pathlib import Path

import pytest

from botbox import Botbox, PiAgent

INTEGRATION = Path(__file__).parents[1] / "integration"
ECHO = json.dumps({"command": "echo hi"})


def sessions(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*.jsonl")}


def contents(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture(scope="module")
def box() -> Botbox:
    return Botbox(PiAgent("openrouter", api_key="unused"), timeout=120)


@pytest.fixture(scope="module")
def first(box: Botbox, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A pi session against the fake model, written to the first run's transcripts."""
    output = tmp_path_factory.mktemp("first")
    command = f"python3 /fake/fake_model_test.py '{ECHO}'"
    result = asyncio.run(box.run(command, mounts=[(INTEGRATION, "/fake", "ro")], output=output))
    assert result.exit_code == 0, (output / "stderr.txt").read_text()
    assert sessions(output / "transcripts"), "pi wrote no session under sessions_dir"
    return output / "transcripts"


@pytest.fixture(scope="module")
def before(first: Path) -> dict[str, bytes]:
    """The first run's transcripts, read before anything is seeded from them."""
    return contents(first)


@pytest.fixture(scope="module")
def second(
    box: Botbox,
    first: Path,
    before: dict[str, bytes],  # noqa: ARG001
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    """A run seeded from `first` that lists the sessions it can see, then starts its own."""
    output = tmp_path_factory.mktemp("second")
    root = f"{box.agent.home}/{box.agent.sessions_dir}"
    command = (
        f"(cd {root} && find . -name '*.jsonl' | cut -c3- | sort > /tmp/seen)"
        f" && python3 /fake/fake_model_test.py '{ECHO}' > /dev/null"
        " && cat /tmp/seen"
    )
    result = asyncio.run(
        box.run(
            command,
            mounts=[(INTEGRATION, "/fake", "ro")],
            output=output,
            transcripts=first,
        )
    )
    assert result.exit_code == 0, (output / "stderr.txt").read_text()
    return output


def describe_a_seeded_pi_run() -> None:
    def it_sees_the_earlier_sessions_under_sessions_dir(first: Path, second: Path) -> None:
        seen = set((second / "stdout.txt").read_text().split())
        assert seen == sessions(first)

    def it_keeps_the_earlier_sessions_and_adds_its_own(first: Path, second: Path) -> None:
        kept = sessions(second / "transcripts")
        assert sessions(first) < kept

    @pytest.mark.usefixtures("second")
    def it_leaves_the_earlier_transcripts_unchanged(first: Path, before: dict[str, bytes]) -> None:
        assert contents(first) == before
