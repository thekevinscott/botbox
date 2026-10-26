from dataclasses import FrozenInstanceError

import pytest

from adocker.Mount.Mount import Mount


def describe_Mount() -> None:
    def it_is_read_write_unless_asked() -> None:
        assert Mount("bind", "/src", "/dst").volume_flag == "/src:/dst:rw"

    def it_renders_a_read_only_volume() -> None:
        assert Mount("volume", "vol", "/run", read_only=True).volume_flag == "vol:/run:ro"

    def it_compares_by_value() -> None:
        assert Mount("bind", "/a", "/b") == Mount("bind", "/a", "/b")
        assert Mount("bind", "/a", "/b") != Mount("volume", "/a", "/b")

    def it_cannot_be_changed() -> None:
        with pytest.raises(FrozenInstanceError):
            Mount("bind", "/a", "/b").read_only = True  # type: ignore[misc]
