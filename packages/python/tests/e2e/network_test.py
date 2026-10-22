"""What a real run can and cannot reach.

The image has no curl, so the probes use node: `fetch` with `NODE_USE_ENV_PROXY=1` is a real
HTTPS request through the proxy env the container gets; without it, it tries to go direct.
The raw CONNECT probe reads the proxy's own answer. Two kinds of probe, because a proxy that
admitted everything would still pass every direct one.
"""

import secrets
import subprocess
import time
from collections.abc import Iterator

import pytest
from conftest import LINE, Probe, docker_lines

from botbox import Botbox, ClaudeAgent, RunResult

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
def session(probe: Probe) -> tuple[RunResult, dict[str, str]]:
    return probe(PROBES)


@pytest.fixture(scope="module")
def report(session: tuple[RunResult, dict[str, str]]) -> dict[str, str]:
    return session[1]


@pytest.fixture(scope="module")
def proxy(session: tuple[RunResult, dict[str, str]]) -> str:
    return session[0].proxy


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
        assert 'Proxying refused on filtered domain "example.com"' in proxy


def describe_allow() -> None:
    def it_admits_an_extra_host() -> None:
        with Botbox(ClaudeAgent(), allow=["example.com"]) as box:
            result = box.run(f"{CONNECT} example.com {PROXY}")
        assert result.stdout.strip() == "200"
        assert 'Established connection to host "example.com"' in result.proxy


@pytest.fixture(scope="module")
def other_run() -> Iterator[str]:
    """Another run's proxy, live, admitting example.com: its address on the default bridge."""
    before = set(docker_lines("ps", "--format", "{{.Names}}"))
    with Botbox(ClaudeAgent(), allow=["example.com"]) as box, box.session() as live:
        (proxy,) = {
            n
            for n in docker_lines("ps", "--format", "{{.Names}}")
            if n.startswith("botbox-proxy-") and n not in before
        }
        (ip,) = docker_lines(
            "inspect", "-f", "{{.NetworkSettings.Networks.bridge.IPAddress}}", proxy
        )
        yield ip
        live.close()


def describe_another_runs_proxy() -> None:
    def it_is_out_of_reach_of_this_run(box: Botbox, other_run: str) -> None:
        result = box.run(f"{CONNECT} example.com {other_run}:8888")
        assert result.stdout.strip() == "error ENETUNREACH", result.stdout


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
        *("--user", "root", "--entrypoint", "node", box.build(), "-e", UPSTREAM),
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
def plain_http(upstream: tuple[str, str]) -> tuple[dict[str, str], str]:
    """Plain-HTTP requests to an allowed host, and what that host saw."""
    name, ip = upstream
    probes = {
        "port 80": f'{REQUEST} {PROXY} "GET http://{ip}/ HTTP/1.0||"',
        "other port": f'{REQUEST} {PROXY} "GET http://{ip}:8022/ HTTP/1.0||"',
        "other port by host": f'{REQUEST} {PROXY} "GET / HTTP/1.0|Host: {ip}:8022||"',
    }
    script = "".join(LINE.format(name=n, command=c) + "\n" for n, c in probes.items())
    with Botbox(ClaudeAgent(), allow=[ip]) as box:
        result = box.run(script)
    fields = (line.split("\t", 1) for line in result.stdout.splitlines() if "\t" in line)
    return {n: v.strip() for n, v in fields}, upstream_log(name)


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
