import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from unittest.mock import ANY, AsyncMock, Mock, call, patch

import pytest

from botbox.home.Home import STAGE, Home

TOKEN = "0123456789ab"


@pytest.fixture
def agent() -> Mock:
    agent = Mock(home="/home/user", sessions_dir=".claude/projects")
    agent.stage_auth.side_effect = lambda home: (home / ".credentials").write_text("token")
    return agent


@pytest.fixture
def steps() -> list[str]:
    return []


@pytest.fixture
def staged() -> dict[str, Any]:
    """What the staging dir held when it was copied in."""
    return {}


@pytest.fixture(autouse=True)
def tmpdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def volume(steps: list[str]) -> Iterator[Mock]:
    with patch("botbox.home.Home.Volume", autospec=True) as m:
        m.return_value.name = f"botbox-home-{TOKEN}"
        m.return_value.__aenter__.side_effect = lambda: steps.append("create volume")
        m.return_value.__aexit__.side_effect = lambda *_: steps.append("remove volume")
        yield m


@pytest.fixture(autouse=True)
def image(steps: list[str], staged: dict[str, Any]) -> Iterator[Mock]:
    async def copy_in(source: Path, target: str) -> None:
        steps.append(f"copy to {target}")
        staged["path"] = source
        staged["mode"] = source.stat().st_mode & 0o777
        staged["files"] = sorted(p.relative_to(source).as_posix() for p in source.rglob("*"))

    with patch("botbox.home.Home.Image", autospec=True) as m:
        stager = m.return_value.create.return_value
        stager.name = f"botbox-stage-{TOKEN}"
        stager.copy_in.side_effect = copy_in
        yield m


@pytest.fixture
def stager(image: Mock) -> Mock:
    created: Mock = image.return_value.create.return_value
    return created


@pytest.fixture(autouse=True)
def remove_within(steps: list[str]) -> Iterator[AsyncMock]:
    async def remove(container: Any) -> None:
        steps.append(f"remove {container.name}")

    with patch("botbox.home.Home.remove_within", autospec=True, side_effect=remove) as m:
        yield m


def describe_Home() -> None:
    def it_is_a_volume_named_and_labelled_after_the_run(agent: Mock, volume: Mock) -> None:
        home = Home(agent, "img", TOKEN)
        assert home.volume is volume.return_value
        volume.assert_called_once_with(
            f"botbox-home-{TOKEN}", labels={"botbox.run": TOKEN}, on_error=ANY
        )

    def it_warns_when_the_volume_cannot_be_removed(agent: Mock, volume: Mock) -> None:
        Home(agent, "img", TOKEN)
        unremoved = volume.call_args.kwargs["on_error"]
        with pytest.warns(RuntimeWarning, match=f"remove its volume botbox-home-{TOKEN}: gone"):
            unremoved(OSError("gone"))

    def it_mounts_its_home_dir_at_the_agents_home(agent: Mock, volume: Mock) -> None:
        home = Home(agent, "img", TOKEN)
        assert home.mount() is volume.return_value.mount.return_value
        volume.return_value.mount.assert_called_once_with("/home/user", subpath="home")

    async def it_stages_copies_and_cleans_up_in_order(agent: Mock, steps: list[str]) -> None:
        async with Home(agent, "img", TOKEN):
            steps.append("use")
        assert steps == [
            "create volume",
            f"copy to {STAGE}/home",
            f"remove botbox-stage-{TOKEN}",
            "use",
            "remove volume",
        ]

    async def it_stages_the_login_and_sessions_dir(
        agent: Mock, staged: dict[str, Any], tmpdir: Path
    ) -> None:
        async with Home(agent, "img", TOKEN):
            pass
        [called] = agent.stage_auth.call_args.args
        assert called == staged["path"]
        assert called.name == "home"
        assert called.parent.parent == tmpdir
        assert called.parent.name.startswith(f"botbox-{TOKEN}-")
        assert staged["files"] == [".claude", ".claude/projects", ".credentials"]

    async def it_removes_the_staging_dir_before_the_block(
        agent: Mock, staged: dict[str, Any]
    ) -> None:
        async with Home(agent, "img", TOKEN):
            assert not staged["path"].parent.exists()

    async def it_keeps_the_home_to_its_owner_whatever_the_umask(
        agent: Mock, staged: dict[str, Any]
    ) -> None:
        previous = os.umask(0)
        try:
            async with Home(agent, "img", TOKEN):
                pass
        finally:
            os.umask(previous)
        assert staged["mode"] == 0o700

    @pytest.mark.parametrize(("uid", "gid"), [(1003, 1005), (2456, 3456)])
    async def it_copies_through_an_unstarted_container_as_the_host_user(
        agent: Mock, image: Mock, monkeypatch: pytest.MonkeyPatch, uid: int, gid: int
    ) -> None:
        monkeypatch.setattr(os, "getuid", lambda: uid)
        monkeypatch.setattr(os, "getgid", lambda: gid)
        async with Home(agent, "img", TOKEN) as home:
            pass
        volume = cast("Mock", home.volume)
        image.assert_called_once_with("img")
        image.return_value.create.assert_awaited_once_with(
            "true",
            name=f"botbox-stage-{TOKEN}",
            labels={"botbox.run": TOKEN},
            user=f"{uid}:{gid}",
            mounts=[volume.mount.return_value],
        )
        assert volume.mount.call_args_list == [call(STAGE)]

    async def it_removes_the_stager_and_volume_when_the_copy_fails(
        agent: Mock, stager: Mock, steps: list[str]
    ) -> None:
        stager.copy_in.side_effect = OSError("no space")
        with pytest.raises(OSError, match="no space"):
            async with Home(agent, "img", TOKEN):
                pass
        assert steps == ["create volume", f"remove botbox-stage-{TOKEN}", "remove volume"]

    async def it_removes_the_volume_when_staging_fails(
        agent: Mock, image: Mock, steps: list[str]
    ) -> None:
        agent.stage_auth.side_effect = PermissionError("no credentials")
        with pytest.raises(PermissionError):
            async with Home(agent, "img", TOKEN):
                pass
        image.return_value.create.assert_not_called()
        assert steps == ["create volume", "remove volume"]

    async def it_warns_when_the_stager_cannot_be_removed(
        agent: Mock, remove_within: AsyncMock
    ) -> None:
        remove_within.side_effect = OSError("daemon gone")
        with pytest.warns(
            RuntimeWarning, match=f"remove its staging container botbox-stage-{TOKEN}"
        ):
            async with Home(agent, "img", TOKEN):
                pass
