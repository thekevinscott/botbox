"""The credential proxy's Envoy config against the pinned Envoy image."""

import asyncio
import io
import json
import os
import subprocess
import tempfile
from collections.abc import Awaitable, Callable
from http.client import HTTPResponse
from pathlib import Path
from uuid import uuid4

from botbox.credential_proxy import Credential, Injection, envoy_config, sds_secret
from botbox.credential_proxy.envoy_config import IMAGE, SECRET_DIR, SECRET_FILE
from botbox.credential_proxy.preloaded import preloaded
from botbox.lockdown import Lockdown, lockdown

ENVOY_USER = "101:101"
VALIDATE = 'cat >"$1"; exec envoy --mode validate --log-level warn --config-yaml "$2"'


def validate(config: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--interactive",
            "--user",
            ENVOY_USER,
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--tmpfs",
            f"{SECRET_DIR}:uid=101,gid=101,mode=0700",
            "--entrypoint",
            "sh",
            IMAGE,
            "-c",
            VALIDATE,
            "sh",
            SECRET_FILE,
            config,
        ],
        input=sds_secret("Bearer placeholder"),
        capture_output=True,
        timeout=120,
    )


def describe_envoy_config() -> None:
    def it_passes_envoys_validation() -> None:
        injection = Injection(
            "api.anthropic.com", "/v1/messages(/count_tokens)?", "Authorization", ("x-api-key",)
        )
        result = validate(envoy_config(injection, "/run/botbox/credentials.sock"))
        assert result.returncode == 0, result.stdout + result.stderr
        assert b"OK" in result.stdout

    def it_passes_with_nothing_to_strip() -> None:
        injection = Injection("chatgpt.com", "/backend-api/codex/responses", "Authorization")
        result = validate(envoy_config(injection, "/run/botbox/credentials.sock"))
        assert result.returncode == 0, result.stdout + result.stderr

    def it_fails_a_regex_re2_rejects() -> None:
        injection = Injection("api.anthropic.com", "(?<=a)b", "Authorization")
        result = validate(envoy_config(injection, "/run/botbox/credentials.sock"))
        assert result.returncode != 0


CLAUDE = Injection(
    "api.anthropic.com", "/v1/messages(/count_tokens)?", "Authorization", ("x-api-key",)
)
# A third-party echo of the request's headers, so the injected value shows. Dummy values only.
ECHO = Injection("postman-echo.com", "/headers", "Authorization", methods=("GET",))


class Raw:
    """Bytes read off a socket, for `HTTPResponse` to parse."""

    def __init__(self, data: bytes) -> None:
        self.data = data

    def makefile(self, *_: object) -> io.BytesIO:
        return io.BytesIO(self.data)


async def request(jail: Lockdown, method: str, path: str) -> str:
    """Send a request to the credential socket from the tinyproxy sidecar, which shares its
    volume, and return the response body. Envoy drops a client that half-closes, so socat
    holds its side open until Envoy closes."""
    assert jail.credentials is not None
    body = b"{}" if method == "POST" else b""
    head = (
        f"{method} {path} HTTP/1.1\r\nhost: localhost\r\nx-api-key: client\r\n"
        "anthropic-version: 2023-06-01\r\ncontent-type: application/json\r\n"
        f"content-length: {len(body)}\r\nconnection: close\r\n\r\n"
    )
    stdin = preloaded(head.encode() + body)
    out = bytearray()
    try:
        await jail.proxy.exec(
            "socat",
            "-,ignoreeof",
            f"UNIX-CONNECT:{jail.credentials.socket}",
            stdin=stdin,
            stdout=out.extend,
        )
    finally:
        os.close(stdin)
    response = HTTPResponse(Raw(bytes(out)))  # type: ignore[arg-type]
    response.begin()
    return response.read().decode()


async def through_proxy[T](
    injection: Injection, secret: str, steps: Callable[[Lockdown], Awaitable[T]]
) -> T:
    token = uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix=f"botbox-{token}-") as scratch:
        async with lockdown(
            (), Path(scratch), token, credential=Credential(injection, secret)
        ) as jail:
            assert jail.credentials is not None
            name = jail.credentials.container.name
            result = await steps(jail)
        assert not docker_lines("ps", "-a", "--filter", f"name={name}", "-q")
        return result


def docker_lines(*args: str) -> list[str]:
    return subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True
    ).stdout.split()


def describe_credential_proxy() -> None:
    def it_sends_the_secret_upstream_on_an_allowed_path() -> None:
        async def steps(jail: Lockdown) -> str:
            return await request(jail, "POST", "/v1/messages")

        body = asyncio.run(through_proxy(CLAUDE, "Bearer not-a-real-token", steps))
        assert json.loads(body)["error"]["message"] == "Invalid bearer token"

    def it_refuses_other_paths() -> None:
        async def steps(jail: Lockdown) -> str:
            return await request(jail, "GET", "/v1/models")

        body = asyncio.run(through_proxy(CLAUDE, "Bearer not-a-real-token", steps))
        assert body == "botbox credential proxy: path not allowed\n"

    def it_refuses_other_methods_on_an_allowed_path() -> None:
        async def steps(proxy: CredentialProxy) -> str:
            return await asyncio.to_thread(request, proxy.socket, "GET", "/v1/messages")

        body = asyncio.run(through_proxy(CLAUDE, "Bearer not-a-real-token", steps))
        assert body == "botbox credential proxy: path not allowed\n"

    def it_sends_a_rotated_secret_from_the_next_request() -> None:
        async def steps(jail: Lockdown) -> list[str]:
            assert jail.credentials is not None
            first = await request(jail, "GET", "/headers")
            await jail.credentials.rotate("Bearer two")
            second = await request(jail, "GET", "/headers")
            return [json.loads(body)["headers"]["authorization"] for body in (first, second)]

        assert asyncio.run(through_proxy(ECHO, "Bearer one", steps)) == ["Bearer one", "Bearer two"]
