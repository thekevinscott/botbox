"""A run as a host uid the image has no passwd entry for."""

import os

import pytest
from conftest import Probe

PROBES = {
    "whoami": "whoami 2>&1",
    "git": "HOME=/tmp EMAIL=agent@example.com git var GIT_COMMITTER_IDENT >/dev/null 2>&1"
    " && echo ok || echo failed",
}


@pytest.fixture(scope="module")
def report(probe: Probe) -> dict[str, str]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "getuid", lambda: 1003)
        patch.setattr(os, "getgid", lambda: 1005)
        _, report = probe(PROBES)
    return report


def describe_an_unnamed_host_uid() -> None:
    def it_gets_a_name(report: dict[str, str]) -> None:
        assert report["whoami"] == "user"

    def it_lets_git_find_an_identity(report: dict[str, str]) -> None:
        assert report["git"] == "ok"
