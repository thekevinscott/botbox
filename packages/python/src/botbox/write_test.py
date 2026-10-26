from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any
from unittest.mock import patch

import pytest

from botbox.write import write


@pytest.fixture
def failing() -> Iterator[dict[Path, str]]:
    """Make a target fail where its value says: "open", "write", "flush" or "close"."""
    fails: dict[Path, str] = {}
    real_open = Path.open

    class Failing:
        def __init__(self, file: IO[bytes], path: Path) -> None:
            self.file, self.path = file, path

        def __getattr__(self, step: str) -> Any:
            if fails.get(self.path) == step:

                def fail(*_args: object) -> None:
                    self.file.close()
                    raise OSError(f"no {step}")

                return fail
            return getattr(self.file, step)

    def opened(path: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if mode != "wb":
            return real_open(path, mode, *args, **kwargs)
        if fails.get(path) == "open":
            raise OSError("no open")
        return Failing(real_open(path, mode, *args, **kwargs), path)

    with patch.object(Path, "open", opened):
        yield fails


def describe_write() -> None:
    def it_writes_each_chunk_to_every_target(tmp_path: Path) -> None:
        a, b = tmp_path / "a", tmp_path / "b"
        b.write_bytes(b"old")
        with write(a, b) as sink:
            sink(b"one ")
            assert a.read_bytes() == b.read_bytes() == b"one "
            sink(b"two")
        assert a.read_bytes() == b.read_bytes() == b"one two"

    def it_writes_to_one_target(tmp_path: Path) -> None:
        with write(tmp_path / "a") as sink:
            sink(b"x")
        assert (tmp_path / "a").read_bytes() == b"x"

    def it_raises_when_the_first_cannot_be_opened(tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError), write(tmp_path / "gone" / "a"):
            pass

    def it_drops_another_that_cannot_be_opened(tmp_path: Path) -> None:
        a, b = tmp_path / "a", tmp_path / "gone" / "b"
        with pytest.warns(RuntimeWarning, match=f"stopped writing to {b}"), write(a, b) as sink:
            sink(b"x")
        assert a.read_bytes() == b"x"

    def it_raises_when_the_first_fails_a_write(tmp_path: Path, failing: dict[Path, str]) -> None:
        a, b = tmp_path / "a", tmp_path / "b"
        failing[a] = "flush"
        with pytest.raises(OSError, match="no flush"), write(a, b) as sink:
            sink(b"x")

    @pytest.mark.parametrize("step", ["write", "flush"])
    def it_drops_another_that_fails_a_write_and_carries_on(
        tmp_path: Path, failing: dict[Path, str], step: str
    ) -> None:
        a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
        with write(a, b, c) as sink:
            sink(b"one ")
            failing[b] = step
            with pytest.warns(RuntimeWarning, match=f"stopped writing to {b}: no {step}"):
                sink(b"two")
            sink(b" three")
        assert a.read_bytes() == c.read_bytes() == b"one two three"
        assert b.read_bytes().startswith(b"one ")
        assert b"three" not in b.read_bytes()

    def it_drops_another_that_fails_to_close(tmp_path: Path, failing: dict[Path, str]) -> None:
        a, b = tmp_path / "a", tmp_path / "b"
        failing[b] = "close"
        with (
            pytest.warns(RuntimeWarning, match=f"stopped writing to {b}: no close"),
            write(a, b) as sink,
        ):
            sink(b"x")
        assert a.read_bytes() == b"x"

    def it_raises_when_the_first_fails_to_close_after_closing_the_rest(
        tmp_path: Path, failing: dict[Path, str]
    ) -> None:
        a, b = tmp_path / "a", tmp_path / "b"
        failing[a] = "close"
        with pytest.raises(OSError, match="no close"), write(a, b) as sink:
            sink(b"x")
        assert b.read_bytes() == b"x"

    def it_closes_every_target_when_the_block_raises(tmp_path: Path) -> None:
        a, b = tmp_path / "a", tmp_path / "b"
        with pytest.raises(KeyError), write(a, b) as sink:
            sink(b"x")
            raise KeyError
        assert a.read_bytes() == b.read_bytes() == b"x"
