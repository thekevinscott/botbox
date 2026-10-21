"""What a real run can and cannot reach.

The image has no curl, so the probes use node: `fetch` with `NODE_USE_ENV_PROXY=1` is a real
HTTPS request through the proxy env the container gets; without it, it tries to go direct.
The raw CONNECT probe reads the proxy's own answer. Two kinds of probe, because a proxy that
admitted everything would still pass every direct one.
"""

import subprocess

import pytest
from conftest import Probe, docker_lines

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

RESOLVE = (
    'node -e \'require("dns").lookup'
    '(process.argv[1], (e) => console.log(e ? "unresolvable" : "resolved"))\''
)

PROXY = '"${HTTPS_PROXY#http://}"'

IP_LITERAL = "140.82.121.4"

PROBES = {
    "proxied anthropic": f"NODE_USE_ENV_PROXY=1 {FETCH} https://api.anthropic.com",
    "proxied example": f"NODE_USE_ENV_PROXY=1 {FETCH} https://example.com",
    "direct example": f"{FETCH} https://example.com",
    "direct anthropic": f"{FETCH} https://api.anthropic.com",
    "connect anthropic": f"{CONNECT} api.anthropic.com {PROXY}",
    "connect example": f"{CONNECT} example.com {PROXY}",
    "connect ip": f"{CONNECT} {IP_LITERAL} {PROXY}",
    "resolve": f"{RESOLVE} example.com",
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


def describe_a_direct_request() -> None:
    def it_reaches_nothing(report: dict[str, str]) -> None:
        assert (report["direct example"], report["direct anthropic"]) == ("failed", "failed")

    def it_cannot_resolve_an_external_name(report: dict[str, str]) -> None:
        assert report["resolve"] == "unresolvable"


def describe_the_proxy_log() -> None:
    def it_records_the_admission(proxy: str) -> None:
        assert 'Established connection to host "api.anthropic.com"' in proxy

    def it_records_the_refusal(proxy: str) -> None:
        assert 'Proxying refused on filtered domain "example.com"' in proxy


def describe_allow() -> None:
    def it_admits_an_extra_host() -> None:
        box = Botbox(ClaudeAgent(), allow=["example.com"])
        result = box.run(f"{CONNECT} example.com {PROXY}")
        assert result.stdout.strip() == "200"
        assert 'Established connection to host "example.com"' in result.proxy


OUTSIDER_CONNECT = (
    "printf 'CONNECT example.com:443 HTTP/1.1\\r\\nHost: example.com:443\\r\\n\\r\\n'"
    ' | nc -w 5 "$0" 8888 | head -n 1'
)


def describe_a_container_outside_the_run() -> None:
    def it_is_refused_by_the_proxy() -> None:
        """The proxy also sits on the default bridge, where any container can reach it."""
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
            answer = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "bridge",
                    "--entrypoint",
                    "sh",
                    "botbox-proxy:latest",
                    "-c",
                    OUTSIDER_CONNECT,
                    ip,
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            live.close()
        assert " 200 " not in answer
