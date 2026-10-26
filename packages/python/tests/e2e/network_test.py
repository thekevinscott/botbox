"""What a real run can and cannot reach.

The image has no curl, so the probes use node: `fetch` with `NODE_USE_ENV_PROXY=1` is a real
HTTPS request through the proxy env the container gets; without it, it tries to go direct.
The raw CONNECT probe reads the proxy's own answer. Two kinds of probe, because a proxy that
admitted everything would still pass every direct one.
"""

import asyncio
import secrets
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import docker_lines, run_probes

from botbox import Botbox, ClaudeAgent

FETCH = (
    "node -e 'fetch(process.argv[1]).then("
    '(r) => console.log(r.status), () => console.log("failed"))\''
)

CONNECT = (
    "node -e 'const [host, proxy] = process.argv.slice(1);"
    ' const [name, port] = proxy.split(":");'
    ' const s = require("net").connect({ host: name, port: Number(port), timeout: 5000 });'
    " const r = (v) => { console.log(v); process.exit(0) };"
    ' s.on("connect", () => s.write('
    '"CONNECT " + host + ":443 HTTP/1.1\\r\\nHost: " + host + ":443\\r\\n\\r\\n"));'
    ' s.on("data", (d) => r(d.toString().split(" ")[1]));'
    ' s.on("timeout", () => r("timeout"));'
    ' s.on("error", (e) => r("error " + e.code))\''
)

REQUEST = (
    "node -e 'const [proxy, request] = process.argv.slice(1);"
    ' const [name, port] = proxy.split(":");'
    ' const s = require("net").connect({ host: name, port: Number(port), timeout: 5000 });'
    " const r = (v) => { console.log(v); process.exit(0) };"
    ' s.on("connect", () => s.write(request.replaceAll("|", "\\r\\n")));'
    ' s.on("data", (d) => r(d.toString().split(" ")[1]));'
    ' s.on("timeout", () => r("timeout"));'
    ' s.on("error", (e) => r("error " + e.code))\''
)

RESOLVE = (
    'node -e \'require("dns").lookup'
    '(process.argv[1], (e) => console.log(e ? "unresolvable" : "resolved"))\''
)

PROXY = '"${HTTPS_PROXY#http://}"'

IP_LITERAL = "140.82.121.4"

METADATA = "169.254.169.254"

PROBES = {
    "proxied anthropic": f"NODE_USE_ENV_PROXY=1 {FETCH} https://api.anthropic.com",
    "proxied example": f"NODE_USE_ENV_PROXY=1 {FETCH} https://example.com",
    "direct example": f"{FETCH} https://example.com",
    "direct anthropic": f"{FETCH} https://api.anthropic.com",
    "connect anthropic": f"{CONNECT} api.anthropic.com {PROXY}",
    "connect example": f"{CONNECT} example.com {PROXY}",
    "connect ip": f"{CONNECT} {IP_LITERAL} {PROXY}",
    "resolve": f"{RESOLVE} example.com",
    "direct metadata": f"{FETCH} http://{METADATA}/latest/meta-data/",
    "proxied metadata": f"NODE_USE_ENV_PROXY=1 {FETCH} http://{METADATA}/latest/meta-data/",
    "connect metadata": f"{CONNECT} {METADATA} {PROXY}",
    "interfaces": "tail -n +3 /proc/net/dev | cut -d: -f1 | tr -d ' '",
    "sockets": "ls -A /run/botbox",
    "write sockets": "touch /run/botbox/planted 2>&1 || true",
}


@pytest.fixture(scope="module")
def report(box: Botbox, output: Path) -> dict[str, str]:
    return run_probes(box, PROBES, output)


@pytest.fixture(scope="module")
def proxy(report: dict[str, str], output: Path) -> str:  # noqa: ARG001
    return (output / "proxy.log").read_text(errors="replace")


def describe_a_request_through_the_proxy() -> None:
    def it_reaches_the_agents_host(report: dict[str, str]) -> None:
        """Any HTTP status: the request got there and back."""
        assert report["proxied anthropic"].isdigit()

    def it_is_refused_anywhere_else(report: dict[str, str]) -> None:
        assert report["proxied example"] == "failed"

    def it_gets_a_200_connect_for_the_agents_host(report: dict[str, str]) -> None:
        assert report["connect anthropic"] == "200"

    def it_gets_a_403_connect_anywhere_else(report: dict[str, str]) -> None:
        assert report["connect example"] == "403"

    def it_gets_a_403_connect_for_an_ip_literal(report: dict[str, str]) -> None:
        assert report["connect ip"] == "403"

    def it_refuses_the_metadata_address(report: dict[str, str]) -> None:
        assert report["proxied metadata"] in {"403", "failed"}
        assert report["connect metadata"] == "403"


def describe_a_direct_request() -> None:
    def it_reaches_nothing(report: dict[str, str]) -> None:
        assert (report["direct example"], report["direct anthropic"]) == ("failed", "failed")

    def it_cannot_resolve_an_external_name(report: dict[str, str]) -> None:
        assert report["resolve"] == "unresolvable"

    def it_cannot_reach_the_metadata_address(report: dict[str, str]) -> None:
        assert report["direct metadata"] == "failed"

    def it_has_only_loopback(report: dict[str, str]) -> None:
        assert report["interfaces"] == "lo"


def describe_the_socket_directory() -> None:
    def it_holds_only_the_proxys_socket(report: dict[str, str]) -> None:
        assert report["sockets"] == "proxy.sock"

    def it_is_read_only_to_the_agent(report: dict[str, str]) -> None:
        assert "Read-only file system" in report["write sockets"]


def describe_the_proxy_log() -> None:
    def it_records_the_admission(proxy: str) -> None:
        assert 'Established connection to host "api.anthropic.com"' in proxy

    def it_records_the_refusal(proxy: str) -> None:
        assert 'Proxying refused on filtered url "example.com:443"' in proxy


def describe_allow() -> None:
    def it_admits_an_extra_host(tmp_path: Path) -> None:
        box = Botbox(ClaudeAgent(), allow=["example.com"])
        asyncio.run(box.run(f"{CONNECT} example.com {PROXY}", output=tmp_path))
        assert (tmp_path / "stdout.txt").read_text().strip() == "200"
        proxy = (tmp_path / "proxy.log").read_text(errors="replace")
        assert 'Established connection to host "example.com"' in proxy


class TokenAgent(ClaudeAgent):
    """Records its run's token: the temp home's parent, botbox-<token>-*, names it."""

    token: str

    def stage_auth(self, home: Path) -> None:
        super().stage_auth(home)
        self.token = home.parent.name.split("-")[1]


@pytest.fixture(scope="module")
def other_run() -> Iterator[str]:
    """Another run's proxy, live, admitting example.com: its address on the default bridge.

    The session is held open on a thread of its own, with its own event loop, for the module.
    """
    agent = TokenAgent()
    up, done = threading.Event(), threading.Event()

    async def hold() -> None:
        async with Botbox(agent, allow=["example.com"]).session():
            up.set()
            await asyncio.to_thread(done.wait)

    holder = threading.Thread(target=asyncio.run, args=(hold(),))
    holder.start()
    try:
        assert up.wait(120)
        (ip,) = docker_lines(
            "inspect",
            "-f",
            "{{.NetworkSettings.Networks.bridge.IPAddress}}",
            f"botbox-proxy-{agent.token}",
        )
        yield ip
    finally:
        done.set()
        holder.join()


def describe_another_runs_proxy() -> None:
    def it_is_out_of_reach_of_this_run(box: Botbox, other_run: str, tmp_path: Path) -> None:
        asyncio.run(box.run(f"{CONNECT} example.com {other_run}:8888", output=tmp_path))
        stdout = (tmp_path / "stdout.txt").read_text()
        assert stdout.strip() == "error ENETUNREACH", stdout


def describe_a_container_outside_the_run() -> None:
    def it_is_refused_by_the_proxy(other_run: str) -> None:
        """The proxy sits on the default bridge, where any container can reach its address."""
        outsider = [
            *("docker", "run", "--rm", "--network", "bridge", "--entrypoint", "sh"),
            *("botbox-claude:latest", "-c", f"{CONNECT} example.com $0:8888", other_run),
        ]
        answer = subprocess.run(outsider, check=True, capture_output=True, text=True).stdout
        assert answer.strip() == "error ECONNREFUSED"


UPSTREAM = (
    'const http = require("http");'
    " for (const port of [80, 8022]) {"
    ' const server = http.createServer((q, r) => r.end("upstream"));'
    ' server.on("connection", () => console.log("connection " + port));'
    ' server.listen(port, () => console.log("listening " + port)); }'
)


@pytest.fixture(scope="module")
def upstream(box: Botbox) -> Iterator[tuple[str, str]]:
    """A server on the default bridge, on 80 and 8022, that logs each connection it accepts."""
    name = f"botbox-e2e-upstream-{secrets.token_hex(6)}"
    server = [
        *("docker", "run", "--detach", "--rm", "--name", name, "--network", "bridge"),
        *("--user", "root", "--entrypoint", "node", asyncio.run(box.build()), "-e", UPSTREAM),
    ]
    subprocess.run(server, check=True, capture_output=True)
    try:
        while "listening 8022" not in upstream_log(name):
            time.sleep(0.1)
        (ip,) = docker_lines(
            "inspect", "-f", "{{.NetworkSettings.Networks.bridge.IPAddress}}", name
        )
        yield name, ip
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=True, capture_output=True)


def upstream_log(name: str) -> str:
    return subprocess.run(
        ["docker", "logs", name], check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture(scope="module")
def plain_http(
    upstream: tuple[str, str], tmp_path_factory: pytest.TempPathFactory
) -> tuple[dict[str, str], str]:
    """Plain-HTTP requests to an allowed host, and what that host saw."""
    name, ip = upstream
    probes = {
        "port 80": f'{REQUEST} {PROXY} "GET http://{ip}/ HTTP/1.0||"',
        "other port": f'{REQUEST} {PROXY} "GET http://{ip}:8022/ HTTP/1.0||"',
        "other port by host": f'{REQUEST} {PROXY} "GET / HTTP/1.0|Host: {ip}:8022||"',
    }
    output = tmp_path_factory.mktemp("plain-http")
    report = run_probes(Botbox(ClaudeAgent(), allow=[ip]), probes, output)
    return report, upstream_log(name)


def describe_plain_http_to_an_allowed_host() -> None:
    def it_reaches_port_80(plain_http: tuple[dict[str, str], str]) -> None:
        report, seen = plain_http
        assert report["port 80"] == "200"
        assert "connection 80\n" in seen

    def it_is_refused_on_any_other_port(plain_http: tuple[dict[str, str], str]) -> None:
        report, _ = plain_http
        assert report["other port"] == "403"

    def it_is_refused_on_any_other_port_named_in_the_host_header(
        plain_http: tuple[dict[str, str], str],
    ) -> None:
        report, _ = plain_http
        assert report["other port by host"] == "403"

    def it_never_connects_to_the_other_port(plain_http: tuple[dict[str, str], str]) -> None:
        _, seen = plain_http
        assert "connection 8022" not in seen
