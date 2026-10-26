import os
import warnings
from pathlib import Path
from tempfile import TemporaryDirectory
from types import TracebackType
from typing import Self

from adocker import Container, Image, Mount, Volume
from botbox.agents.agent import Agent
from botbox.process import settle
from botbox.remove_within import remove_within
from botbox.warned import warned

STAGE = "/botbox-stage"
SUBPATH = "home"


class Home:
    """The agent's home for one run: directory `home` in volume `botbox-home-<token>`, labelled
    `botbox.run=<token>`.

    Entering stages the agent's login and its `sessions_dir` in a host temp dir named after the
    token, copies that into the volume through a container created from `image` and never
    started, then removes both. The copy is owner-only and owned by this process's uid, the
    agent's; a mount point Docker made would be root's. Leaving removes the volume, and a
    removal that fails is a warning.
    """

    def __init__(self, agent: Agent, image: str, token: str) -> None:
        self.agent = agent
        self.image = image
        self.token = token
        self.volume = Volume(
            f"botbox-home-{token}", labels={"botbox.run": token}, on_error=self._unremoved
        )

    async def __aenter__(self) -> Self:
        await self.volume.__aenter__()
        try:
            await self._stage()
        except BaseException as error:
            await self.volume.__aexit__(type(error), error, error.__traceback__)
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.volume.__aexit__(exc_type, exc, tb)

    def mount(self) -> Mount:
        """The home mounted at the agent's home path, for `Image.run`'s `mounts`."""
        return self.volume.mount(self.agent.home, subpath=SUBPATH)

    async def _stage(self) -> None:
        with TemporaryDirectory(prefix=f"botbox-{self.token}-") as staging:
            home = Path(staging) / SUBPATH
            home.mkdir(mode=0o700)
            self.agent.stage_auth(home)
            (home / self.agent.sessions_dir).mkdir(parents=True, exist_ok=True)
            name = f"botbox-stage-{self.token}"
            stager = Container(name)
            try:
                stager = await Image(self.image).create(
                    "true",
                    name=name,
                    labels={"botbox.run": self.token},
                    user=f"{os.getuid()}:{os.getgid()}",
                    mounts=[self.volume.mount(STAGE)],
                )
                await stager.copy_in(home, f"{STAGE}/{SUBPATH}")
            finally:
                await settle(warned(remove_within(stager), f"remove its staging container {name}"))

    def _unremoved(self, error: Exception) -> None:
        warnings.warn(
            f"botbox could not remove its volume {self.volume.name}: {error}",
            RuntimeWarning,
            stacklevel=1,
        )
