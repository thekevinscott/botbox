import os
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory, TemporaryFile

from adocker.DockerException import DockerException
from adocker.run import run
from botbox.agents.agent import Agent
from botbox.process import settle
from botbox.remove_within import remove_within
from botbox.warned import warned

# Not the agent's home: an empty volume mounted where the image has files gets a copy of them.
MOUNT = "/botbox-home"
ERROR_BYTES = 64 * 1024


async def stage_home(agent: Agent, image: str, volume: str, token: str) -> None:
    """Fill `volume` with the agent's home: its staged credentials and an empty `sessions_dir`.

    The files are staged in a host temp directory, deleted before this returns, and streamed as a
    tar into a root container that unpacks them and gives the home to this process's uid, mode
    0700. That container is labelled `botbox.run=<token>` and removed, through any cancel. One
    that exits non-zero raises `DockerException`.
    """
    with TemporaryFile() as archive:
        with TemporaryDirectory(prefix=f"botbox-{token}-") as staging:
            home = Path(staging)
            agent.stage_auth(home)
            # Docker would create the mount point root-owned.
            (home / agent.sessions_dir).mkdir(parents=True, exist_ok=True)
            with tarfile.open(fileobj=archive, mode="w") as tar:
                tar.add(home, arcname=".")
        archive.seek(0)
        name = f"botbox-stage-{token}"
        owner = f"{os.getuid()}:{os.getgid()}"
        args = [
            "--interactive",
            "--name",
            name,
            "--label",
            f"botbox.run={token}",
            "--user",
            "0:0",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            *("--cap-add", "CHOWN", "--cap-add", "DAC_OVERRIDE", "--cap-add", "FOWNER"),
            "--security-opt",
            "no-new-privileges",
            "--log-driver",
            "none",
            "--volume",
            f"{volume}:{MOUNT}:rw",
            image,
            "sh",
            "-c",
            f"tar -x -C {MOUNT} && chown -R {owner} {MOUNT} && chmod 700 {MOUNT}",
        ]
        errors = bytearray()
        try:
            code = await run(args, stdin=archive, stdout=errors, stderr=errors, limit=ERROR_BYTES)
        finally:
            await settle(warned(remove_within(name), f"remove its home container {name}"))
    if code != 0:
        raise DockerException(["docker", "run", *args], code, errors.decode(errors="replace"))
