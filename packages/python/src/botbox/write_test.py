from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any
from unittest.mock import Mock, patch

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
        a, b, c = tmp_path / "z", tmp_path / "b", tmp_path / "c"
        with write(a, b, c) as sink:
            sink(b"one ")
            failing[b] = step
            with pytest.warns(RuntimeWarning, match=f"stopped writing to {b}: no {step}") as caught:
                sink(b"two")
            assert caught[0].filename == __file__
            sink(b" three")
        assert a.read_bytes() == c.read_bytes() == b"one two three"
        assert b.read_bytes().startswith(b"one ")
        assert b"three" not in b.read_bytes()

    def it_drops_another_that_fails_to_close(tmp_path: Path, failing: dict[Path, str]) -> None:
        a, b = tmp_path / "z", tmp_path / "b"
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

    def describe_with_filter_line() -> None:
        def it_passes_each_whole_line_with_its_newline_however_chunked(tmp_path: Path) -> None:
            seen: list[bytes] = []

            def see(line: bytes) -> bytes:
                seen.append(line)
                return line

            with write(tmp_path / "a", filter_line=see) as sink:
                for chunk in (b"on", b"e\ntw", b"o\n\nthree\n", b"x" * 70_000, b"\n"):
                    sink(chunk)
            assert seen == [b"one\n", b"two\n", b"\n", b"three\n", b"x" * 70_000 + b"\n"]

        def it_writes_what_the_filter_returns_and_drops_none(tmp_path: Path) -> None:
            with write(tmp_path / "a", filter_line=filter_line) as sink:
                sink(b"one\ndrop\ntwo\n")
            assert (tmp_path / "a").read_bytes() == b"ONE\nTWO\n"

        def it_passes_the_unterminated_rest_on_leaving(tmp_path: Path) -> None:
            with write(tmp_path / "a", filter_line=filter_line) as sink:
                sink(b"one\nrest")
                assert (tmp_path / "a").read_bytes() == b"ONE\n"
            assert (tmp_path / "a").read_bytes() == b"ONE\nREST"

        def it_drops_the_rest_when_the_block_raises(tmp_path: Path) -> None:
            with pytest.raises(KeyError), write(tmp_path / "a", filter_line=filter_line) as sink:
                sink(b"one\nrest")
                raise KeyError
            assert (tmp_path / "a").read_bytes() == b"ONE\n"

        def it_passes_nothing_for_no_output(tmp_path: Path) -> None:
            filtered = Mock(return_value=None)
            with write(tmp_path / "a", filter_line=filtered) as sink:
                sink(b"")
            filtered.assert_not_called()

        def it_raises_what_the_filter_raises_and_skips_that_line(tmp_path: Path) -> None:
            with (
                pytest.raises(ValueError, match="boom"),
                write(tmp_path / "a", filter_line=filter_line) as sink,
            ):
                sink(b"one\nboom\n")
            assert (tmp_path / "a").read_bytes() == b"ONE\n"

        def it_raises_what_the_filter_raises_for_the_rest_on_leaving(tmp_path: Path) -> None:
            with (
                pytest.raises(ValueError, match="boom"),
                write(tmp_path / "a", filter_line=filter_line) as sink,
            ):
                sink(b"one\nboom")
            assert (tmp_path / "a").read_bytes() == b"ONE\n"


def filter_line(line: bytes) -> bytes | None:
    """Drops b"drop\\n", raises on "boom" and upper-cases the rest."""
    if line.startswith(b"boom"):
        raise ValueError(line)
    return None if line == b"drop\n" else line.upper()
