import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import IO


@contextmanager
def write(*targets: Path) -> Iterator[Callable[[bytes], None]]:
    """Open each of `targets` and yield a sink that writes every chunk to all of them.

    The first must take every chunk: a failure there raises. Any other that fails, on opening
    or on a write, is warned about and dropped while the rest carry on.
    """
    first, *others = targets
    head = first.open("wb")
    files: dict[IO[bytes], Path] = {}
    try:
        for path in others:
            try:
                files[path.open("wb")] = path
            except OSError as error:
                dropped(path, error)

        def sink(chunk: bytes) -> None:
            head.write(chunk)
            head.flush()
            for file, path in list(files.items()):
                try:
                    file.write(chunk)
                    file.flush()
                except OSError as error:
                    del files[file]
                    with suppress(OSError):
                        file.close()
                    dropped(path, error)

        yield sink
    finally:
        try:
            for file, path in reversed(files.items()):
                try:
                    file.close()
                except OSError as error:
                    dropped(path, error)
        finally:
            head.close()


def dropped(path: Path, error: OSError) -> None:
    warnings.warn(f"botbox stopped writing to {path}: {error}", RuntimeWarning, stacklevel=3)
