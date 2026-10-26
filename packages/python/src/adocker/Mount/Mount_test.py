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

    def it_refuses_a_subpath_on_a_bind() -> None:
        with pytest.raises(ValueError, match="only a volume"):
            Mount("bind", "/a", "/b", subpath="c")

    def describe_flag() -> None:
        def it_is_a_volume_flag_without_a_subpath() -> None:
            assert Mount("bind", "/a", "/b", read_only=True).flag == ("--volume", "/a:/b:ro")

        def it_is_a_mount_flag_with_a_subpath() -> None:
            assert Mount("volume", "v", "/h", subpath="home").flag == (
                "--mount",
                "type=volume,source=v,target=/h,volume-subpath=home",
            )

        def it_marks_a_read_only_subpath() -> None:
            assert Mount("volume", "v", "/h", read_only=True, subpath="home").flag == (
                "--mount",
                "type=volume,source=v,target=/h,volume-subpath=home,readonly",
            )
