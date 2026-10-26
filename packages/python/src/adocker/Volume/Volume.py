from collections.abc import Callable, Mapping
from types import TracebackType

from adocker.Mount import Mount
from adocker.utils import run_docker, settle
from adocker.Volume.remove_volume import remove_volume

REMOVE_SECONDS = 30


class Volume:
    """A named volume with `labels`, created on entering and removed on leaving.

    The removal runs to the end through any number of cancels, and gives up with TimeoutError
    after `remove_seconds`. A removal that fails goes to `on_error` if given. Without it, the
    failure is raised, unless the block already raised, whose error it never replaces.
    """

    def __init__(
        self,
        name: str,
        *,
        labels: Mapping[str, str] | None = None,
        remove_seconds: float = REMOVE_SECONDS,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self.name = name
        self.labels = dict(labels or {})
        self.remove_seconds = remove_seconds
        self.on_error = on_error

    async def __aenter__(self) -> "Volume":
        flags = [flag for item in self.labels.items() for flag in ("--label", "=".join(item))]
        await run_docker("volume", "create", *flags, self.name)
        return self

    async def __aexit__(
        self,
        _type: type[BaseException] | None,
        error: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        try:
            await settle(remove_volume(self.name, self.remove_seconds))
        except Exception as failure:
            if self.on_error is not None:
                self.on_error(failure)
            elif error is None:
                raise

    def mount(self, target: str, *, read_only: bool = False, subpath: str | None = None) -> Mount:
        """This volume, or its directory `subpath`, mounted at `target` in a container, for
        `Image.run`'s `mounts`."""
        return Mount("volume", self.name, target, read_only, subpath)
