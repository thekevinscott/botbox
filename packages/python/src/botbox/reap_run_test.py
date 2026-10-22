import fcntl
import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, call, patch

import pytest

from botbox.reap_run import reap_run

TOKEN = "0123456789ab"
PS = ("ps", "--all", "--quiet", "--filter", f"label=botbox.run={TOKEN}")


@pytest.fixture
def lock(tmp_path: Path) -> Path:
    (tmp_path / TOKEN / "home").mkdir(parents=True)
    (tmp_path / TOKEN / "home" / ".credentials").write_text("token")
    path = tmp_path / f"{TOKEN}.lock"
    path.touch()
    return path


@pytest.fixture(autouse=True)
def run_docker() -> Iterator[AsyncMock]:
    async def docker(*args: str) -> str:
        return "c1\nc2\n" if args[0] == "ps" else ""

    with patch("botbox.reap_run.run_docker", autospec=True, side_effect=docker) as m:
        yield m


def held(lock: Path) -> int:
    fd = os.open(lock, os.O_RDONLY)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


def describe_reap_run() -> None:
    def describe_when_the_owner_is_dead() -> None:
        async def it_removes_the_runs_containers_whatever_their_state(
            lock: Path, run_docker: AsyncMock
        ) -> None:
            assert await reap_run(lock) is True
            assert run_docker.await_args_list == [call(*PS), call("rm", "--force", "c1", "c2")]

        async def it_removes_the_temp_home_then_the_lock_file(lock: Path) -> None:
            await reap_run(lock)
            assert list(lock.parent.iterdir()) == []

        async def it_skips_removal_when_no_container_is_left(
            lock: Path, run_docker: AsyncMock
        ) -> None:
            run_docker.side_effect = None
            run_docker.return_value = ""
            assert await reap_run(lock) is True
            assert run_docker.await_args_list == [call(*PS)]

        async def it_keeps_the_run_for_the_next_sweep_when_docker_fails(
            lock: Path, run_docker: AsyncMock
        ) -> None:
            run_docker.side_effect = OSError("daemon gone")
            with pytest.warns(
                RuntimeWarning, match=f"^botbox could not reap run {TOKEN}: daemon gone$"
            ):
                assert await reap_run(lock) is False
            assert lock.exists()
            assert (lock.parent / TOKEN / "home" / ".credentials").exists()

        async def it_keeps_the_lock_file_when_the_home_will_not_go(lock: Path) -> None:
            with (
                patch("botbox.reap_run.remove_tree", side_effect=PermissionError("agent's")),
                pytest.warns(RuntimeWarning, match="agent's"),
            ):
                assert await reap_run(lock) is False
            assert lock.exists()

        async def it_lets_go_of_the_lock(lock: Path) -> None:
            await reap_run(lock)
            lock.touch()
            os.close(held(lock))

    def describe_when_the_owner_lives() -> None:
        async def it_leaves_the_run_alone(lock: Path, run_docker: AsyncMock) -> None:
            fd = held(lock)
            try:
                assert await reap_run(lock) is False
            finally:
                os.close(fd)
            run_docker.assert_not_awaited()
            assert (lock.parent / TOKEN / "home" / ".credentials").exists()
            assert lock.exists()

    async def it_does_nothing_for_a_lock_file_already_gone(
        lock: Path, run_docker: AsyncMock
    ) -> None:
        lock.unlink()
        assert await reap_run(lock) is False
        run_docker.assert_not_awaited()

    async def it_does_nothing_when_another_sweep_removed_it_first(
        lock: Path, run_docker: AsyncMock
    ) -> None:
        unlink = Path.unlink
        opened = os.open

        def open_then_lose_the_race(path: Path, flags: int) -> int:
            fd = opened(path, flags)
            unlink(path)
            return fd

        with patch("botbox.reap_run.os.open", side_effect=open_then_lose_the_race):
            assert await reap_run(lock) is False
        run_docker.assert_not_awaited()
