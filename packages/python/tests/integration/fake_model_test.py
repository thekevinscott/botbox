"""Runs pi in a container against a fake model that makes one bash call, then says done.

`python3 fake_model_test.py '<bash arguments as JSON>' [pi args...]` serves an
OpenAI-compatible model on loopback, points pi at it through models.json and runs `pi -p` in
json mode. Named `_test` so the checks treat it as test code, not source.
"""

import http.server
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any


def chunk(delta: dict[str, Any], finish: str | None = None) -> dict[str, Any]:
    choice = {"index": 0, "delta": delta, "finish_reason": finish}
    return {"id": "c", "object": "chat.completion.chunk", "model": "fake", "choices": [choice]}


class Model(http.server.BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if any(message["role"] == "tool" for message in body["messages"]):
            chunks = [chunk({"role": "assistant", "content": "done"}), chunk({}, "stop")]
        else:
            function = {"name": "bash", "arguments": sys.argv[1]}
            call = {"index": 0, "id": "call_1", "type": "function", "function": function}
            chunks = [chunk({"role": "assistant", "tool_calls": [call]}), chunk({}, "tool_calls")]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for each in chunks:
            self.wfile.write(f"data: {json.dumps(each)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, format: str, *args: Any) -> None:
        pass


def main() -> int:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Model)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    provider = {
        "baseUrl": f"http://127.0.0.1:{server.server_port}/v1",
        "api": "openai-completions",
        "apiKey": "unused",
        "models": [{"id": "fake"}],
    }
    agent_dir = Path(os.environ["PI_CODING_AGENT_DIR"])
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "models.json").write_text(json.dumps({"providers": {"fake": provider}}))
    pi = ["pi", "-p", "go", "--mode", "json", "--provider", "fake", "--model", "fake"]
    return subprocess.run([*pi, *sys.argv[2:]]).returncode


if __name__ == "__main__":
    sys.exit(main())
