"""The credential proxy's Envoy config against the pinned Envoy image."""

import asyncio
import json
import subprocess
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import uuid4

from botbox.credential_proxy import Injection, envoy_config, sds_secret
from botbox.credential_proxy.credential_proxy import credential_proxy
from botbox.credential_proxy.CredentialProxy import CredentialProxy
from botbox.credential_proxy.envoy_config import IMAGE, SECRET_DIR, SECRET_FILE
from botbox.lockdown import lockdown

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


def request(socket: Path, method: str, path: str) -> str:
    return subprocess.run(
        ["curl", "-sS", "-X", method, "--unix-socket", str(socket), "-H", "x-api-key: client"]
        + ["-H", "anthropic-version: 2023-06-01", "-H", "content-type: application/json"]
        + (["-d", "{}"] if method == "POST" else [])
        + [f"http://localhost{path}"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout


async def through_proxy[T](
    injection: Injection, secret: str, steps: Callable[..., Awaitable[T]]
) -> T:
    token = uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix=f"botbox-{token}-") as scratch:
        async with lockdown((), Path(scratch), token) as jail:
            log = Path(scratch) / "envoy.log"
            async with credential_proxy(
                injection, secret, proxy=jail.proxy, sockets=jail.sockets, token=token, log=log
            ) as proxy:
                result = await steps(proxy)
            assert not docker_lines("ps", "-a", "--filter", f"name={proxy.name}", "-q")
            return result


def docker_lines(*args: str) -> list[str]:
    return subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True
    ).stdout.split()


def describe_credential_proxy() -> None:
    def it_sends_the_secret_upstream_on_an_allowed_path() -> None:
        async def steps(proxy: CredentialProxy) -> str:
            return await asyncio.to_thread(request, proxy.socket, "POST", "/v1/messages")

        body = asyncio.run(through_proxy(CLAUDE, "Bearer not-a-real-token", steps))
        assert json.loads(body)["error"]["message"] == "Invalid bearer token"

    def it_refuses_other_paths() -> None:
        async def steps(proxy: CredentialProxy) -> str:
            return await asyncio.to_thread(request, proxy.socket, "GET", "/v1/models")

        body = asyncio.run(through_proxy(CLAUDE, "Bearer not-a-real-token", steps))
        assert body == "botbox credential proxy: path not allowed\n"
