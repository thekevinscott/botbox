import dataclasses

import pytest

from botbox.Limits import Limits


def describe_limits() -> None:
    def it_caps_nothing_by_default() -> None:
        assert Limits().args() == []

    def it_passes_both_caps_to_docker_run() -> None:
        assert Limits(memory="2g", pids=1024).args() == ["--memory", "2g", "--pids-limit", "1024"]

    def it_leaves_out_a_cap_set_to_none() -> None:
        assert Limits(memory=None, pids=7).args() == ["--pids-limit", "7"]
        assert Limits(memory="1g", pids=None).args() == ["--memory", "1g"]
        assert Limits(memory=None, pids=None).args() == []

    def it_takes_keywords_only() -> None:
        with pytest.raises(TypeError):
            Limits("2g")  # type: ignore[call-arg]

    def it_is_frozen() -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            Limits().pids = 1  # type: ignore[misc]

    def it_has_no_instance_dict() -> None:
        assert not hasattr(Limits(), "__dict__")
