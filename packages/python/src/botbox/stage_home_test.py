import os
import tarfile
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any
from unittest.mock import Mock, patch

import pytest

from adocker.DockerException import DockerException
from botbox.stage_home import stage_home

TOKEN = "0123456789ab"
NAME = "botbox-stage-0123456789ab"


@pytest.fixture
def agent() -> Mock:
    agent = Mock(sessions_dir=".claude/projects")

    def stage(home: Path) -> None:
        agent.staged = home
        (home / ".credentials").write_text("token")

    agent.stage_auth.side_effect = stage
    return agent


@pytest.fixture
def seen() -> dict[str, Any]:
    """What the fake `docker run` was handed."""
    return {}


@pytest.fixture(autouse=True)
def run(agent: Mock, seen: dict[str, Any]) -> Iterator[Mock]:
    async def attached(args: list[str], *, stdin: IO[bytes], stderr: bytearray, **_: Any) -> int:
        seen["args"] = args
        seen["staged_after"] = agent.staged.exists()
        with tarfile.open(fileobj=stdin) as tar:
            seen["members"] = {m.name: m for m in tar.getmembers()}
            credentials = tar.extractfile("./.credentials")
            assert credentials is not None
            seen["credentials"] = credentials.read()
        stderr.extend(b"tar: no space\n")
        return int(seen.get("code", 0))

    with patch("botbox.stage_home.run", autospec=True, side_effect=attached) as m:
        yield m


@pytest.fixture(autouse=True)
def remove() -> Iterator[Mock]:
    async def removed(_name: str) -> None:
        pass

    with patch("botbox.stage_home.remove_within", autospec=True, side_effect=removed) as m:
        yield m


def describe_stage_home() -> None:
    async def it_streams_the_staged_credentials_and_sessions_dir_as_a_tar(
        agent: Mock, seen: dict[str, Any]
    ) -> None:
        await stage_home(agent, "an-agent:latest", "botbox-home-x", TOKEN)
        assert seen["credentials"] == b"token"
        assert seen["members"]["./.claude/projects"].isdir()

    async def it_deletes_the_staging_directory_before_docker_runs(
        agent: Mock, seen: dict[str, Any]
    ) -> None:
        await stage_home(agent, "an-agent:latest", "botbox-home-x", TOKEN)
        assert agent.staged.name.startswith(f"botbox-{TOKEN}-")
        assert seen["staged_after"] is False

    async def it_unpacks_as_root_with_only_the_caps_it_needs_and_no_network(
        agent: Mock, seen: dict[str, Any]
    ) -> None:
        await stage_home(agent, "an-agent:latest", "botbox-home-x", TOKEN)
        owner = f"{os.getuid()}:{os.getgid()}"
        assert seen["args"] == [
            "--interactive",
            "--name",
            NAME,
            "--label",
            f"botbox.run={TOKEN}",
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
            "botbox-home-x:/botbox-home:rw",
            "an-agent:latest",
            "sh",
            "-c",
            f"tar -x -C /botbox-home && chown -R {owner} /botbox-home && chmod 700 /botbox-home",
        ]

    async def it_removes_its_container(agent: Mock, remove: Mock) -> None:
        await stage_home(agent, "an-agent:latest", "botbox-home-x", TOKEN)
        remove.assert_awaited_once_with(NAME)

    async def it_raises_what_docker_said_when_the_unpack_fails(
        agent: Mock, seen: dict[str, Any], remove: Mock
    ) -> None:
        seen["code"] = 2
        with pytest.raises(DockerException) as raised:
            await stage_home(agent, "an-agent:latest", "botbox-home-x", TOKEN)
        assert (raised.value.return_code, raised.value.stderr) == (2, "tar: no space\n")
        remove.assert_awaited_once_with(NAME)

    async def it_removes_its_container_when_docker_raises(
        agent: Mock, run: Mock, remove: Mock
    ) -> None:
        run.side_effect = OSError("no docker")
        with pytest.raises(OSError, match="no docker"):
            await stage_home(agent, "an-agent:latest", "botbox-home-x", TOKEN)
        remove.assert_awaited_once_with(NAME)

    async def it_warns_when_its_container_will_not_go(agent: Mock, remove: Mock) -> None:
        remove.side_effect = RuntimeError("busy")
        with pytest.warns(
            RuntimeWarning, match=f"^botbox could not remove its home container {NAME}"
        ):
            await stage_home(agent, "an-agent:latest", "botbox-home-x", TOKEN)
