"""The posture a real run puts the container in.

Every probe reads what the kernel already publishes; nothing runs an exploit.
"""

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

    def it_runs_as_uid_1000(posture: dict[str, str]) -> None:
        assert posture["uid"] == "1000"

    def it_runs_as_user(posture: dict[str, str]) -> None:
        assert posture["user"] == "user"
