"""Bind mounts and `workdir` in a real run, and the setup errors that stop one before it starts."""

import asyncio
import os
from pathlib import Path

import pytest
from conftest import leftovers, run_probes

from botbox import Botbox

ORIGINAL = "original\n"

PROBES = {
    "ro write": "echo changed > /ro/keep.txt && echo written || echo refused",
    "rw write": "echo made > /rw/new.txt && echo written || echo refused",
    "pwd": "pwd",
}


@pytest.fixture(scope="module")
def host(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("mounts")
    (root / "ro").mkdir()
    (root / "ro" / "keep.txt").write_text(ORIGINAL)
    (root / "rw").mkdir()
    return root


@pytest.fixture(scope="module")
def report(box: Botbox, host: Path, output: Path) -> dict[str, str]:
    mounts = [(host / "ro", "/ro", "ro"), (host / "rw", "/rw", "rw")]
    return run_probes(box, PROBES, output, mounts=mounts, workdir="/rw")


def describe_a_read_only_mount() -> None:
    def it_cannot_be_written(report: dict[str, str]) -> None:
        assert report["ro write"].endswith("refused")

    def it_leaves_the_host_file_unchanged(report: dict[str, str], host: Path) -> None:
        assert report
        assert (host / "ro" / "keep.txt").read_text() == ORIGINAL


def describe_a_read_write_mount() -> None:
    def it_can_be_written(report: dict[str, str]) -> None:
        assert report["rw write"] == "written"

    def it_lands_the_write_on_the_host(report: dict[str, str], host: Path) -> None:
        assert report
        assert (host / "rw" / "new.txt").read_text() == "made\n"

    def it_lands_the_write_owned_by_the_host_user(report: dict[str, str], host: Path) -> None:
        assert report
        assert (host / "rw" / "new.txt").stat().st_uid == host.stat().st_uid


def describe_workdir() -> None:
    def it_starts_the_command_there(report: dict[str, str]) -> None:
        assert report["pwd"] == "/rw"

    def it_raises_outside_every_mount_before_any_container(box: Botbox, tmp_path: Path) -> None:
        before = leftovers()
        with pytest.raises(ValueError, match="workdir"):
            asyncio.run(
                box.run(
                    "true",
                    output=tmp_path / "output",
                    mounts=[(tmp_path, "/rw", "rw")],
                    workdir="/elsewhere",
                )
            )
        assert leftovers() == before


def describe_a_missing_host_path() -> None:
    def it_is_created_owned_by_the_host_user_and_writable(box: Botbox, tmp_path: Path) -> None:
        missing = tmp_path / "new" / "out"
        result = asyncio.run(
            box.run(
                "echo made > /out/x.txt",
                output=tmp_path / "output",
                mounts=[(missing, "/out", "rw")],
            )
        )
        assert result.exit_code == 0
        assert missing.stat().st_uid == os.getuid()
        assert (missing / "x.txt").read_text() == "made\n"
