import asyncio
import os
import warnings
from collections.abc import Iterator
from typing import Any
from unittest.mock import Mock, patch

import pytest

from botbox.credential_proxy.CredentialProxy import ROTATE, CredentialProxy


class Exec:
    def __init__(self) -> None:
        self.command: tuple[str, ...] = ()
        self.stdin = b""
        self.stdin_fd = -1
        self.raises: Exception | None = None

    async def __call__(self, *command: str, **options: Any) -> str:
        self.command = command
        self.stdin_fd = options["stdin"]
        self.stdin = os.read(options["stdin"], 1 << 16)
        if self.raises is not None:
            raise self.raises
        return ""


class Expired(Exception):
    """Stands in for `CredentialsExpired`."""


class CommandFailed(Exception):
    """Stands in for the SDK's `DockerException`."""


class Source:
    """A credential source that hands out `reads` in turn, then cancels the follow."""

    def __init__(self, *reads: str | Exception) -> None:
        self.reads = list(reads)
        self.env: dict[str, str] = {}

    def read(self) -> Mock:
        if not self.reads:
            raise asyncio.CancelledError
        value = self.reads.pop(0)
        if isinstance(value, Exception):
            raise value
        return Mock(secret=value)


class Sent:
    """container.exec for rotations: each secret sent, failing while `failing` holds any."""

    def __init__(self) -> None:
        self.secrets: list[bytes] = []
        self.failing: list[Exception] = []

    async def __call__(self, *_command: str, **options: Any) -> str:
        sent = os.read(options["stdin"], 1 << 16)
        if self.failing:
            raise self.failing.pop(0)
        self.secrets.append(sent)
        return ""


async def follow(source: Source, sent: str = "Bearer one") -> list[bytes]:
    exec_ = Sent()
    proxy = CredentialProxy(Mock(exec=exec_), "/s")
    with pytest.raises(asyncio.CancelledError):
        await proxy.follow(source, sent)
    return exec_.secrets


@pytest.fixture(autouse=True)
def collaborators() -> Iterator[None]:
    with (
        patch(f"{__package__}.CredentialProxy.SECRET_FILE", "/secrets/s.json"),
        patch(f"{__package__}.CredentialProxy.sds_secret", lambda value: f"sds {value}".encode()),
        patch(f"{__package__}.CredentialProxy.FOLLOW_SECONDS", 0),
        patch(f"{__package__}.CredentialProxy.CredentialsExpired", Expired),
        patch(f"{__package__}.CredentialProxy.DockerException", CommandFailed),
    ):
        yield


@pytest.fixture
def container() -> Mock:
    return Mock(exec=Exec())


def describe_CredentialProxy() -> None:
    def it_holds_its_container_and_socket(container: Mock) -> None:
        proxy = CredentialProxy(container, "/s/c.sock")
        assert proxy.container is container
        assert proxy.socket == "/s/c.sock"

    def describe_rotate() -> None:
        async def it_renames_the_new_secret_over_the_file_in_its_container(
            container: Mock,
        ) -> None:
            await CredentialProxy(container, "/s").rotate("Bearer two")
            execute = container.exec
            assert execute.command == ("sh", "-c", ROTATE, "sh", "/secrets/s.json")
            assert ROTATE == 'cat >"$1.next" && mv "$1.next" "$1"'
            assert execute.stdin == b"sds Bearer two"

        async def it_closes_the_pipe(container: Mock) -> None:
            await CredentialProxy(container, "/s").rotate("v")
            with pytest.raises(OSError):
                os.fstat(container.exec.stdin_fd)

        async def it_raises_what_docker_raised_and_closes_the_pipe(container: Mock) -> None:
            execute = container.exec
            execute.raises = RuntimeError("No such container: p")
            with pytest.raises(RuntimeError, match="No such container: p"):
                await CredentialProxy(container, "/s").rotate("v")
            with pytest.raises(OSError):
                os.fstat(execute.stdin_fd)

    def describe_follow() -> None:
        async def it_sends_nothing_while_the_secret_is_the_one_sent() -> None:
            assert await follow(Source("Bearer one", "Bearer one")) == []

        async def it_rotates_to_a_changed_secret_once() -> None:
            secrets = await follow(Source("Bearer one", "Bearer two", "Bearer two"))
            assert secrets == [b"sds Bearer two"]

        async def it_rotates_again_on_each_change() -> None:
            secrets = await follow(Source("Bearer two", "Bearer one"))
            assert secrets == [b"sds Bearer two", b"sds Bearer one"]

        @pytest.mark.parametrize(
            "error",
            [FileNotFoundError("gone"), ValueError("half written"), Expired("expired")],
        )
        async def it_skips_a_check_it_cannot_read(error: Exception) -> None:
            secrets = await follow(Source(error, "Bearer two"))
            assert secrets == [b"sds Bearer two"]

        async def it_tries_a_failed_rotation_again_next_time() -> None:
            exec_ = Sent()
            exec_.failing.append(CommandFailed("daemon away"))
            proxy = CredentialProxy(Mock(exec=exec_), "/s")
            with pytest.raises(asyncio.CancelledError):
                await proxy.follow(Source("Bearer two", "Bearer two"), "Bearer one")
            assert exec_.secrets == [b"sds Bearer two"]

        async def it_lets_any_other_error_out() -> None:
            exec_ = Sent()
            proxy = CredentialProxy(Mock(exec=exec_), "/s")
            with pytest.raises(KeyError):
                await proxy.follow(Source(KeyError("claudeAiOauth")), "Bearer one")

        async def it_waits_between_checks() -> None:
            started = asyncio.get_running_loop().time()
            with patch(f"{__package__}.CredentialProxy.FOLLOW_SECONDS", 0.05):
                await follow(Source("Bearer one"))
            assert asyncio.get_running_loop().time() - started >= 0.1

    def describe_following() -> None:
        async def it_follows_the_source_inside_the_block_and_stops_at_its_end() -> None:
            calls: list[tuple[object, str]] = []
            stopped = asyncio.Event()

            async def follow(source: object, sent: str) -> None:
                calls.append((source, sent))
                try:
                    await asyncio.Event().wait()
                finally:
                    stopped.set()

            proxy = CredentialProxy(Mock(), "/s")
            source = Source()
            with patch.object(proxy, "follow", follow):
                async with proxy.following(source, "Bearer one"):
                    await asyncio.sleep(0)
                    assert calls == [(source, "Bearer one")]
                    assert not stopped.is_set()
                assert stopped.is_set()

        async def it_warns_when_the_follow_failed() -> None:
            async def follow(_source: object, _sent: str) -> None:
                raise KeyError("claudeAiOauth")

            proxy = CredentialProxy(Mock(), "/s")
            with (
                patch.object(proxy, "follow", follow),
                pytest.warns(RuntimeWarning, match=r"new credentials: KeyError\('claudeAiOauth'\)"),
            ):
                async with proxy.following(Source(), "Bearer one"):
                    await asyncio.sleep(0)

        async def it_stops_a_follow_that_never_started() -> None:
            proxy = CredentialProxy(Mock(), "/s")
            started = []

            async def follow(_source: object, _sent: str) -> None:
                started.append(True)

            with patch.object(proxy, "follow", follow), warnings.catch_warnings():
                warnings.simplefilter("error")
                async with proxy.following(Source(), "Bearer one"):
                    pass
            assert started == []
