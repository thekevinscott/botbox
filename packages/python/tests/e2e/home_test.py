"""The per-run temporary home a real run mounts at the agent's home path."""

from pathlib import Path

import pytest
from conftest import leftovers, run_probes

from botbox import Botbox

PROBES = {
    "home": "echo $HOME",
    "pwd": "pwd",
    "credentials": "test -s ~/.claude/.credentials.json && echo present || echo missing",
    "writable": "touch ~/scratch && echo written || echo refused",
}


@pytest.fixture(scope="module")
def session(box: Botbox, output: Path) -> tuple[dict[str, str], set[str], set[str]]:
    before = leftovers()
    report = run_probes(box, PROBES, output)
    return report, before, leftovers()


@pytest.fixture(scope="module")
def report(session: tuple[dict[str, str], set[str], set[str]]) -> dict[str, str]:
    return session[0]


def describe_the_home() -> None:
    def it_is_the_agents_home(report: dict[str, str]) -> None:
        assert report["home"] == "/home/user"

    def it_is_where_the_command_starts_without_a_workdir(report: dict[str, str]) -> None:
        assert report["pwd"] == "/home/user"

    def it_holds_the_staged_credentials(report: dict[str, str]) -> None:
        assert report["credentials"] == "present"

    def it_is_writable_by_the_agent(report: dict[str, str]) -> None:
        assert report["writable"] == "written"

    def it_is_gone_from_the_host_after_the_run(
        session: tuple[dict[str, str], set[str], set[str]],
    ) -> None:
        _, before, after = session
        assert {e for e in after if e.startswith("temp ")} == {
            e for e in before if e.startswith("temp ")
        }
