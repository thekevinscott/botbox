"""The locked-down agent reaches credential injection only through its loopback relay."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest

from adocker import Image
from botbox import Botbox, ClaudeAgent
from botbox.credential_proxy import Credential, Injection
from botbox.lockdown import CREDENTIALS_ENV, RELAY, lockdown

CREDENTIAL = Credential(
    Injection("api.anthropic.com", "/v1/messages(/count_tokens)?", "Authorization", ("x-api-key",)),
    "Bearer not-a-real-token",
)
REQUESTS = r"""
const http = require('node:http');
function request(path, method) {
  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: '127.0.0.1', port: 41894, path, method, timeout: 30000,
      headers: {
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json',
        'x-api-key': 'client',
      },
    }, res => {
      let body = '';
      res.on('data', chunk => { body += chunk; });
      res.on('end', () => resolve({status: res.statusCode, body}));
    });
    req.on('error', reject);
    req.end(method === 'POST' ? '{}' : undefined);
  });
}
(async () => {
  console.log(JSON.stringify(await request('/v1/messages', 'POST')));
  console.log(JSON.stringify(await request('/v1/models', 'GET')));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


@pytest.fixture(scope="module")
def responses(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[list[dict[str, object]], int, str, Path]:
    root = tmp_path_factory.mktemp("credential-relay")
    output = root / "output"
    output.mkdir()
    box = Botbox(ClaudeAgent(api_key="unused"))

    async def probe() -> tuple[list[dict[str, object]], int, str, Path]:
        image = await box.build()
        token = uuid4().hex[:12]
        async with lockdown((), root, token, output, credential=CREDENTIAL) as jail:
            flags = box._lockdown_flags(token, box._home_files(), jail, [], None)  # noqa: SLF001
            stdout, stderr = bytearray(), bytearray()
            agent = await Image(image).run(
                RELAY,
                "node",
                "-e",
                REQUESTS,
                name=f"botbox-agent-{token}",
                rm=True,
                stdout=stdout.extend,
                stderr=stderr.extend,
                **flags,
            )
            assert await agent.wait() == 0, stderr.decode()
            denied_out, denied_err = bytearray(), bytearray()
            flags["user"] = "101:101"
            denied = await Image(image).run(
                RELAY,
                "sh",
                "-c",
                "echo reached",
                name=f"botbox-agent-{token}-uid101",
                rm=True,
                stdout=denied_out.extend,
                stderr=denied_err.extend,
                **flags,
            )
            denied_code = await denied.wait()
        return (
            [json.loads(line) for line in stdout.decode().splitlines()],
            denied_code,
            denied_err.decode(),
            output,
        )

    return asyncio.run(probe())


def test_allowed_path_gets_anthropics_invalid_token_response(
    responses: tuple[list[dict[str, object]], int, str, Path],
) -> None:
    allowed = responses[0][0]
    assert allowed["status"] == 401
    assert "Invalid bearer token" in str(allowed["body"])


def test_other_path_gets_the_proxy_refusal(
    responses: tuple[list[dict[str, object]], int, str, Path],
) -> None:
    refused = responses[0][1]
    assert refused == {"status": 403, "body": "botbox credential proxy: path not allowed\n"}
    assert "/v1/messages" in (responses[3] / "credentials.log").read_text()


def test_envoys_uid_is_refused(
    responses: tuple[list[dict[str, object]], int, str, Path],
) -> None:
    assert responses[1] == 125
    assert "credential proxy's uid 101" in responses[2]


@pytest.fixture(scope="module")
def without_socket(tmp_path_factory: pytest.TempPathFactory) -> tuple[int, str]:
    """The relay in a run without a credential proxy, told one was asked for."""
    root = tmp_path_factory.mktemp("credential-relay-missing")
    box = Botbox(ClaudeAgent(api_key="unused"))

    async def probe() -> tuple[int, str]:
        image = await box.build()
        token = uuid4().hex[:12]
        async with lockdown((), root, token) as jail:
            flags = box._lockdown_flags(token, box._home_files(), jail, [], None)  # noqa: SLF001
            flags["env"][CREDENTIALS_ENV] = "1"
            stderr = bytearray()
            agent = await Image(image).run(
                RELAY,
                "sh",
                "-c",
                "echo reached",
                name=f"botbox-agent-{token}",
                rm=True,
                stderr=stderr.extend,
                **flags,
            )
            return await agent.wait(), stderr.decode()

    return asyncio.run(probe())


def test_a_missing_credential_socket_fails_closed(without_socket: tuple[int, str]) -> None:
    code, stderr = without_socket
    assert code == 1
    assert "asked for credential injection" in stderr
    assert "/run/botbox/credentials.sock is missing" in stderr
