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
