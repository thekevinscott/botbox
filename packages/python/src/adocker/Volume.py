from collections.abc import Callable
from types import TracebackType

from adocker.remove_volume import remove_volume
from adocker.run_args import Mount
from adocker.run_docker import run_docker
from adocker.settle import settle

REMOVE_SECONDS = 30


class Volume:
    """A named volume with `label`, created on entering and removed on leaving.

    The removal runs to the end through any number of cancels, and gives up with TimeoutError
    after `remove_seconds`. A removal that fails goes to `on_error` if given. Without it, the
    failure is raised, unless the block already raised, whose error it never replaces.
    """

    def __init__(
        self,
        name: str,
        *,
        label: str,
        remove_seconds: float = REMOVE_SECONDS,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self.name = name
        self.label = label
        self.remove_seconds = remove_seconds
        self.on_error = on_error

    async def __aenter__(self) -> "Volume":
        await run_docker("volume", "create", "--label", self.label, self.name)
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

    def mount(self, target: str, mode: str = "rw") -> Mount:
        """This volume mounted at `target` in a container, for `Image.run`'s `mounts`."""
        return (self.name, target, mode)
