import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import IO


@contextmanager
def write(
    *targets: Path, filter_line: Callable[[bytes], bytes | None] | None = None
) -> Iterator[Callable[[bytes], None]]:
    """Open each of `targets` and yield a sink that writes every chunk to all of them.

    The first must take every chunk: a failure there raises. Any other that fails, on opening
    or on a write, is warned about and dropped while the rest carry on.

    With `filter_line`, chunks are cut into lines, newline kept, and each line is written as
    `filter_line` returns it, or dropped on None. The unterminated rest goes through it on
    leaving the block, unless the block raised.
    """
    with write_all(*targets) as put:
        if filter_line is None:
            yield put
            return
        pending = bytearray()

        def keep(line: bytes) -> None:
            kept = filter_line(line)
            if kept is not None:
                put(kept)

        def sink(chunk: bytes) -> None:
            pending.extend(chunk)
            while (end := pending.find(b"\n") + 1) > 0:
                line = bytes(pending[:end])
                del pending[:end]
                keep(line)

        yield sink
        if pending:
            keep(bytes(pending))


@contextmanager
def write_all(*targets: Path) -> Iterator[Callable[[bytes], None]]:
    first, *others = targets
    files: dict[IO[bytes], Path] = {first.open("wb"): first}
    try:
        for path in others:
            try:
                files[path.open("wb")] = path
            except OSError as error:
                dropped(path, error)

        def sink(chunk: bytes) -> None:
            for file, path in list(files.items()):
                try:
                    file.write(chunk)
                    file.flush()
                except OSError as error:
                    if path is first:
                        raise
                    del files[file]
                    with suppress(OSError):
                        file.close()
                    dropped(path, error)

        yield sink
    finally:
        for file, path in reversed(files.items()):
            try:
                file.close()
            except OSError as error:
                if path is first:
                    raise
                dropped(path, error)


def dropped(path: Path, error: OSError) -> None:
    warnings.warn(f"botbox stopped writing to {path}: {error}", RuntimeWarning, stacklevel=3)
