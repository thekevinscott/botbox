"""ClaudeAgent(tool_timeout=...) run by the real Claude Code in its image, against a fake API.

The fake answers the first turn with a Bash call that outlives the limit, then ends the turn
once it sees the tool result, so what Claude Code did with the call is in the requests.
"""

import asyncio
import json
import subprocess
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from uuid import uuid4

import pytest

from botbox import Botbox, ClaudeAgent

LIMIT = 5
# Not `sleep`: Claude Code never moves a command starting with `sleep` to the background.
COMMAND = "node -e \"setTimeout(() => console.log('finished'), 120000)\""


def sse(blocks: list[dict[str, Any]], stop: str) -> bytes:
    events: list[dict[str, Any]] = [
        {
            "type": "message_start",
            "message": {
                "id": "msg_fake",
                "type": "message",
                "role": "assistant",
                "model": "claude-fake",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        }
    ]
    for index, block in enumerate(blocks):
        if block["type"] == "tool_use":
            start = {**block, "input": {}}
            delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
        else:
            start = {"type": "text", "text": ""}
            delta = {"type": "text_delta", "text": block["text"]}
        events += [
            {"type": "content_block_start", "index": index, "content_block": start},
            {"type": "content_block_delta", "index": index, "delta": delta},
            {"type": "content_block_stop", "index": index},
        ]
    events += [
        {"type": "message_delta", "delta": {"stop_reason": stop}, "usage": {"output_tokens": 1}},
        {"type": "message_stop"},
    ]
    return b"".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode() for e in events)


def tool_results(body: dict[str, Any]) -> list[str]:
    return [
        json.dumps(part.get("content"))
        for message in body.get("messages", [])
        if isinstance(message["content"], list)
        for part in message["content"]
        if part.get("type") == "tool_result"
    ]


@pytest.fixture
def api() -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """A fake Messages API on the host's loopback, and the request bodies it got."""
    requests: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            if tool_results(body) or not body.get("tools"):
                reply = sse([{"type": "text", "text": "done"}], "end_turn")
            else:
                call = {"command": COMMAND, "description": "wait"}
                bash = {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": call}
                reply = sse([bash], "tool_use")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *_: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", requests
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(scope="module")
def image() -> str:
    return asyncio.run(Botbox(ClaudeAgent()).build())


def claude(image: str, url: str, command: str) -> tuple[subprocess.CompletedProcess[str], float]:
    name = f"botbox-test-{uuid4().hex[:12]}"
    start = time.monotonic()
    try:
        done = subprocess.run(
            [
                "docker",
                "run",
                "--name",
                name,
                "--network",
                "host",
                "--env",
                f"ANTHROPIC_BASE_URL={url}",
                "--env",
                "ANTHROPIC_API_KEY=sk-fake",
                image,
                "sh",
                "-c",
                command,
            ],
            capture_output=True,
            text=True,
            timeout=110,
        )
    finally:
        subprocess.run(["docker", "rm", "--force", name], capture_output=True, check=False)
    return done, time.monotonic() - start


def describe_a_bash_call_past_the_tool_timeout() -> None:
    def it_is_killed_at_the_limit_and_the_model_told(
        image: str, api: tuple[str, list[dict[str, Any]]]
    ) -> None:
        url, requests = api
        done, took = claude(image, url, ClaudeAgent(tool_timeout=LIMIT).command("go"))
        assert done.returncode == 0, done.stderr
        assert took < 60
        results = [r for body in requests for r in tool_results(body)]
        assert any(f"Command timed out after {LIMIT}s" in r for r in results), results
        assert not any("moved to the background" in r for r in results)
