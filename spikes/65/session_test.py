"""Three stream-json turns in one session; the proxy's secret is swapped between turns.

  session_test.py <scratch> <credentials.json>

Turn 1 uses the real token, turn 2 a bogus one (a token that expired mid-run), turn 3 the
real one again. Shows whether a running Claude Code recovers once the host token is good.
"""

import json
import subprocess
import sys
from pathlib import Path

here = Path(__file__).parent
scratch, credentials = sys.argv[1], sys.argv[2]
creds = f"{scratch}/creds"
writer = ["uv", "run", "--no-project", "python", str(here / "write_secret.py")]

session = subprocess.Popen(
    [
        str(here / "agent.sh"),
        scratch,
        "claude",
        "-p",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
        "--strict-mcp-config",
        "--model",
        "haiku",
    ],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True,
)


def turn(message: str) -> dict:
    event = {"type": "user", "message": {"role": "user", "content": message}}
    session.stdin.write(json.dumps(event) + "\n")
    session.stdin.flush()
    for line in session.stdout:
        event = json.loads(line)
        if event.get("type") == "result":
            return event
    raise SystemExit("session ended early")


def show(n: int, result: dict) -> None:
    print(n, result.get("is_error"), result.get("api_error_status"), repr(result.get("result"))[:120])


show(1, turn("Run `echo one` with Bash, then reply with its output only."))
subprocess.run([*writer, "literal", "Bearer sk-ant-oat01-expired", creds], check=True)
show(2, turn("Reply with exactly: two"))
subprocess.run([*writer, "oauth", credentials, creds], check=True)
show(3, turn("Reply with exactly: three"))
session.stdin.close()
print("exit", session.wait())
