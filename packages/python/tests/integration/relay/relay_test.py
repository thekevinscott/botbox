"""Every branch of botbox-relay, run directly in the pid namespace of a stand-in proxy.

With BOTBOX_RELAY_KCOV=1 each run goes through kcov, and the session fails unless every line
of the relay ran. kcov runs the script under bash, so that mode does not test dash.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from relay_harness_test import Proxy, Relay, serving, uncovered_lines

from adocker import Dockerfile, Image, Mount, Volume
from botbox import HomeFiles
from botbox.lockdown import CREDENTIALS_ENV, HOME_BYTES_ENV, PROXY_USER, RELAY_DIR

HERE = Path(__file__).parent
KCOV = os.environ.get("BOTBOX_RELAY_KCOV") == "1"
AGENT = "4242:4242"
CREDENTIALS = {CREDENTIALS_ENV: "1"}
FETCH = "socat -u TCP:127.0.0.1:{port} -"


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def image() -> Image:
    dockerfile = Dockerfile(HERE / "Dockerfile")
    return await dockerfile.build("botbox-relay-test", contexts={"botbox": RELAY_DIR})


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def relay(image: Image) -> AsyncIterator[Relay]:
    if not KCOV:
        yield Relay(image, None)
        return
    async with Volume(f"botbox-relay-coverage-{uuid4().hex[:12]}") as coverage:
        yield Relay(image, coverage)
        missed = await uncovered_lines(image, coverage)
    if missed:
        pytest.fail(f"botbox-relay lines never run: {', '.join(missed)}")


@pytest.fixture
async def proxy(image: Image) -> AsyncIterator[Proxy]:
    async with serving(image, "proxy", "credentials") as proxy:
        yield proxy


@pytest.fixture
async def proxy_without_credentials(image: Image) -> AsyncIterator[Proxy]:
    async with serving(image, "proxy") as proxy:
        yield proxy


async def test_refuses_the_proxys_uid(relay: Relay, proxy: Proxy) -> None:
    result = await relay.run(proxy, "echo", "reached", user=PROXY_USER)
    assert result.code == 125
    assert result.stdout == ""
    assert result.stderr == "botbox-relay: the agent runs as the proxy's uid 100; use another\n"


async def test_refuses_the_credential_proxys_uid(relay: Relay, proxy: Proxy) -> None:
    result = await relay.run(proxy, "echo", "reached", user="101:101")
    assert result.code == 125
    assert result.stdout == ""
    assert "credential proxy's uid 101; use another" in result.stderr


async def test_names_a_uid_missing_from_passwd(relay: Relay, proxy: Proxy) -> None:
    result = await relay.run(proxy, "sh", "-c", "whoami; tail -n 1 /etc/passwd", user=AGENT)
    assert result.code == 0, result.stderr
    assert result.stdout == "user\nuser:x:4242:4242:user:/home/user:/bin/sh\n"


async def test_leaves_a_named_uid_alone(relay: Relay, proxy: Proxy) -> None:
    result = await relay.run(proxy, "sh", "-c", "whoami; grep -c ^user: /etc/passwd", user="nobody")
    assert result.stdout == "nobody\n0\n"


async def test_runs_on_when_passwd_is_read_only(relay: Relay, proxy: Proxy, tmp_path: Path) -> None:
    passwd = tmp_path / "passwd"
    passwd.write_text("root:x:0:0:root:/root:/bin/sh\n")
    result = await relay.run(
        proxy,
        "sh",
        "-c",
        "whoami || id -u",
        user=AGENT,
        mounts=[Mount("bind", str(passwd), "/etc/passwd", read_only=True)],
    )
    assert result.code == 0
    assert result.stdout == "4242\n"


async def test_forwards_the_proxy_port(relay: Relay, proxy: Proxy) -> None:
    result = await relay.run(proxy, "sh", "-c", FETCH.format(port=41893), user=AGENT)
    assert result.code == 0, result.stderr
    assert result.stdout == "proxy\n"


async def test_serves_no_credential_port_unasked(relay: Relay, proxy: Proxy) -> None:
    result = await relay.run(proxy, "sh", "-c", FETCH.format(port=41894), user=AGENT)
    assert result.code != 0
    assert result.stdout == ""


async def test_forwards_the_credential_port(relay: Relay, proxy: Proxy) -> None:
    result = await relay.run(
        proxy, "sh", "-c", FETCH.format(port=41894), user=AGENT, env=CREDENTIALS
    )
    assert result.code == 0, result.stderr
    assert result.stdout == "credentials\n"


async def test_fails_closed_without_the_credential_socket(
    relay: Relay, proxy_without_credentials: Proxy
) -> None:
    result = await relay.run(
        proxy_without_credentials, "echo", "reached", user=AGENT, env=CREDENTIALS
    )
    assert result.code == 1
    assert result.stdout == ""
    assert result.stderr == (
        "botbox-relay: the run asked for credential injection,"
        " but /run/botbox/credentials.sock is missing\n"
    )


async def test_gives_up_when_the_proxy_port_never_listens(relay: Relay, proxy: Proxy) -> None:
    path = "/opt/fakes/socat-down:/usr/local/bin:/usr/bin:/bin"
    result = await relay.run(proxy, "echo", "reached", user=AGENT, env={"PATH": path})
    assert result.code == 1
    assert result.stdout == ""
    assert result.stderr == "botbox-relay: nothing listening on 127.0.0.1:41893\n"


async def test_gives_up_when_the_credential_port_never_listens(relay: Relay, proxy: Proxy) -> None:
    path = "/opt/fakes/credentials-down:/usr/local/bin:/usr/bin:/bin"
    env = {**CREDENTIALS, "PATH": path}
    result = await relay.run(proxy, "echo", "reached", user=AGENT, env=env)
    assert result.code == 1
    assert result.stdout == ""
    assert result.stderr == "botbox-relay: nothing listening on 127.0.0.1:41894\n"


async def test_execs_the_command_with_its_arguments(relay: Relay, proxy: Proxy) -> None:
    result = await relay.run(proxy, "sh", "-c", 'echo "$0 $1"; exit 7', "a b", "c", user=AGENT)
    assert result.code == 7
    assert result.stdout == "a b c\n"


def staged() -> tuple[dict[str, str], bytes]:
    home = HomeFiles()
    home.write(".claude/.credentials.json", "placeholder", mode=0o600)
    archive = home.archive()
    return {HOME_BYTES_ENV: str(len(archive))}, archive


async def test_writes_the_staged_files_into_home(relay: Relay, proxy: Proxy) -> None:
    show = "stat -c '%a %u %n' .claude/.credentials.json; cat .claude/.credentials.json"
    size, archive = staged()
    env = {"HOME": "/tmp", **size}
    result = await relay.run(proxy, "sh", "-c", f"cd && {show}", user=AGENT, env=env, stdin=archive)
    assert result.code == 0, result.stderr
    assert result.stdout == "600 4242 .claude/.credentials.json\nplaceholder"


async def test_hands_the_rest_of_stdin_to_the_command(relay: Relay, proxy: Proxy) -> None:
    size, archive = staged()
    env = {"HOME": "/tmp", **size}
    stdin = archive + b"first\nsecond\n"
    result = await relay.run(proxy, "cat", user=AGENT, env=env, stdin=stdin)
    assert result.code == 0, result.stderr
    assert result.stdout == "first\nsecond\n"


async def test_keeps_the_archive_size_out_of_the_commands_env(relay: Relay, proxy: Proxy) -> None:
    size, archive = staged()
    env = {"HOME": "/tmp", **size}
    command = ("sh", "-c", "env | grep -c BOTBOX_HOME")
    result = await relay.run(proxy, *command, user=AGENT, env=env, stdin=archive)
    assert result.stdout == "0\n"


async def test_fails_when_home_is_not_writable(relay: Relay, proxy: Proxy) -> None:
    size, archive = staged()
    env = {"HOME": "/usr", **size}
    result = await relay.run(proxy, "echo", "reached", user=AGENT, env=env, stdin=archive)
    assert result.code == 1
    assert result.stdout == ""
    assert result.stderr.endswith("botbox-relay: could not write the agent's files into /usr\n")
