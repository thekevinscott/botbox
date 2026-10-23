"""The posture a real run puts the container in.

Every probe reads what the kernel already publishes; nothing runs an exploit.
"""

import os

import pytest
from conftest import Probe

EMPTY_CAPABILITY_MASK = "0" * 16

PROBES = {
    "effective": "grep ^CapEff: /proc/self/status | cut -f2",
    "bounding": "grep ^CapBnd: /proc/self/status | cut -f2",
    "no_new_privs": "grep ^NoNewPrivs: /proc/self/status | cut -f2",
    "setuid": "find / -xdev -perm -4000 -type f 2>/dev/null | sort",
    "setgid": "find / -xdev -perm -2000 -type f 2>/dev/null | sort",
    "uid": "id -u",
    "user": "whoami",
    "signal init": "kill -0 1 2>&1 || true",
    "init uid": "awk '/^Uid:/ {print $2}' /proc/1/status",
    "init environ": "cat /proc/1/environ 2>&1 >/dev/null || true",
    "orphan": (
        "o=$( (sleep 0.3 >/dev/null 2>&1 & echo $!) );"
        " parent=$(awk '/^PPid:/ {print $2}' /proc/$o/status); sleep 1;"
        " if [ -e /proc/$o ]; then echo \"$parent $(awk '/^State:/ {print $2}' /proc/$o/status)\";"
        ' else echo "$parent reaped"; fi'
    ),
}


@pytest.fixture(scope="module")
def posture(probe: Probe) -> dict[str, str]:
    return probe(PROBES)[1]


def describe_the_container() -> None:
    def it_has_no_effective_capabilities(posture: dict[str, str]) -> None:
        assert posture["effective"] == EMPTY_CAPABILITY_MASK

    def it_has_an_empty_bounding_set(posture: dict[str, str]) -> None:
        assert posture["bounding"] == EMPTY_CAPABILITY_MASK

    def it_forbids_privilege_escalation(posture: dict[str, str]) -> None:
        assert posture["no_new_privs"] == "1"

    def it_has_no_setuid_binaries(posture: dict[str, str]) -> None:
        assert posture["setuid"] == ""

    def it_has_no_setgid_binaries(posture: dict[str, str]) -> None:
        assert posture["setgid"] == ""

    def it_runs_as_the_host_uid(posture: dict[str, str]) -> None:
        assert posture["uid"] == str(os.getuid())

    def it_runs_as_user(posture: dict[str, str]) -> None:
        assert posture["user"] == "user"


def describe_the_shared_pid_namespace() -> None:
    """The agent lives in the proxy's PID namespace, so it can see the proxy's processes."""

    def it_has_the_proxys_init_as_pid_1(posture: dict[str, str]) -> None:
        assert posture["init uid"] == "100"

    def it_cannot_signal_it(posture: dict[str, str]) -> None:
        assert "not permitted" in posture["signal init"]

    def it_cannot_read_its_environment(posture: dict[str, str]) -> None:
        assert "Permission denied" in posture["init environ"]

    def it_reaps_what_the_agent_orphans(posture: dict[str, str]) -> None:
        """No agent init under --pid container:, so orphans go to the proxy's, which must reap."""
        assert posture["orphan"] == "1 reaped"
