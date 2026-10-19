"""The per-run temporary home a real run mounts at the agent's home path."""

import pytest
from conftest import Probe, leftovers

from botbox import RunResult

PROBES = {
    "home": "echo $HOME",
    "pwd": "pwd",
    "credentials": "test -s ~/.claude/.credentials.json && echo present || echo missing",
    "writable": "touch ~/scratch && echo written || echo refused",
}


@pytest.fixture(scope="module")
def session(probe: Probe) -> tuple[RunResult, dict[str, str], set[str], set[str]]:
    before = leftovers()
    result, report = probe(PROBES)
    return result, report, before, leftovers()


@pytest.fixture(scope="module")
def report(session: tuple[RunResult, dict[str, str], set[str], set[str]]) -> dict[str, str]:
    return session[1]


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
        session: tuple[RunResult, dict[str, str], set[str], set[str]],
    ) -> None:
        _, _, before, after = session
        assert {e for e in after if e.startswith("temp ")} == {
            e for e in before if e.startswith("temp ")
        }
