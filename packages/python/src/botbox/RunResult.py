import shutil
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Self

from botbox.remove_tree import remove_tree


@dataclass(frozen=True, slots=True, weakref_slot=True)
class RunResult:
    """What a run left behind. Nothing parsed.

    `exit_code` is -1 when no exit code came back, including an interrupted session.
    `image` is the tag that ran: the layered tag when a `dockerfile` was given, else the agent's.
    `files` is a temp dir the result owns, deleted when the result is garbage collected, on
    `cleanup()`, or when a `with result:` block ends. A path into it is only good while the
    result lives; `save()` copies it somewhere permanent.
    """

    stdout: str
    stderr: str
    exit_code: int
    image: str
    files: Path
    _finalizer: weakref.finalize[[Path], None] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_finalizer", weakref.finalize(self, remove_tree, self.files))

    @property
    def transcript(self) -> Path:
        """The transcript files, at their paths relative to the agent's home."""
        return self.files / "transcript"

    @property
    def proxy(self) -> Path:
        """The proxy's log: every connection, admitted or refused."""
        return self.files / "proxy.log"

    def save(self, dest: str | Path) -> Path:
        """Copy `files` to `dest`, which must not exist yet, and return it."""
        return Path(shutil.copytree(self.files, dest))

    def cleanup(self) -> None:
        """Delete `files` now. Later calls do nothing."""
        self._finalizer()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.cleanup()
