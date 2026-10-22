"""A fake `docker` on PATH that keeps each container's state; `conftest` puts it there.

Named `_test` so the checks treat it as test code, not source.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

CREDENTIALS = '{"claudeAiOauth": {"accessToken": "t"}}'
REFUSAL = 'NOTICE Proxying refused on filtered url "github.com:443"\n'

# Each container is a state file, `<name>.json`, that inspect reads and rm deletes. The proxy
# serves until its stdin closes; each agent does what the plan says for its command. A session
# answers each message on its stdin with an event, a line that isn't JSON, and a result.
FAKE_DOCKER = """
import json, os, signal, sys, time
from pathlib import Path

argv = sys.argv[1:]
state = Path(os.environ["FAKE_DOCKER_STATE"])
plan = json.loads((state / "plan.json").read_text())
with open(state / "calls.jsonl", "a") as log:
    log.write(json.dumps(argv) + "\\n")


def fail(message, code=1):
    sys.stderr.write(message)
    sys.exit(code)


def option(name):
    return argv[argv.index(name) + 1]


def volume(target):
    mounts = (argv[i + 1].split(":") for i, a in enumerate(argv) if a == "--volume")
    return next(Path(source) for source, t, _ in mounts if t == target)


def settle(name, status, code=0):
    (state / f"{name}.json").write_text(json.dumps({"Status": status, "ExitCode": code}))


command = argv[0]
if command == "buildx":
    if option("--tag") in plan.get("builds_fail", ()):
        fail("ERROR: failed to solve\\n")
    sys.exit(0)
if (state / "down").exists():
    fail("Cannot connect to the Docker daemon\\n")
if command == "version":
    print("{}")
elif command == "container":
    name = argv[-1]
    path = state / f"{name}.json"
    if not path.exists():
        fail(f"Error: No such container: {name}\\n")
    print(json.dumps([{"Name": "/" + name, "State": json.loads(path.read_text())}]))
elif command == "rm":
    time.sleep(plan.get("rm_seconds", 0))
    if plan.get("rm_fails"):
        fail("Error response from daemon: removal of container is already in progress\\n")
    (state / f"{argv[-1]}.json").unlink(missing_ok=True)
elif option("--name").startswith("botbox-proxy-"):
    name = option("--name")
    if plan.get("proxy_fails"):
        fail("tinyproxy: bad config\\n")
    settle(name, "running")
    log = volume("/var/log/tinyproxy") / "tinyproxy.log"
    log.write_bytes(plan.get("proxy_log", "").encode("latin-1"))
    if plan.get("proxy_log_unreadable"):
        log.unlink()
        log.mkdir()
    (volume("/run/botbox") / "proxy.sock").touch()
    sys.stdin.buffer.read()
    settle(name, "exited")
else:
    name = option("--name")
    agent = plan["agents"].get(argv[-1], {})
    if agent.get("missing"):
        fail("Unable to find image 'botbox-claude:latest' locally\\n", 125)
    settle(name, "running")
    session = volume("/home/user") / ".claude" / "projects" / "-work"
    session.mkdir(parents=True)
    (session / "abc.jsonl").write_text('{"type": "user"}\\n')
    sys.stdout.write(agent.get("stdout", ""))
    sys.stderr.write(agent.get("stderr", ""))
    sys.stdout.flush()
    sys.stderr.flush()
    mode = agent.get("mode")
    if mode == "session":
        for line in sys.stdin:
            said = json.loads(line)["message"]["content"]
            print(json.dumps({"type": "assistant", "said": said}), flush=True)
            if said == "hang":
                (state / f"{name}.hanging").touch()
                time.sleep(600)
            if said == "die":
                os.kill(os.getpid(), signal.SIGKILL)
            print("not json")
            print(json.dumps({"type": "result", "result": said.upper()}), flush=True)
    if mode == "hang":
        (state / f"{name}.hanging").touch()
        time.sleep(600)
    if mode == "daemon_gone":
        (state / "down").touch()
        sys.exit(125)
    if mode == "client_dies":
        os.kill(os.getpid(), signal.SIGKILL)
    if mode == "client_dies_after_exit":
        settle(name, "exited", 0)
        os.kill(os.getpid(), signal.SIGKILL)
    settle(name, "exited", agent.get("exit", 0))
    sys.exit(agent.get("exit", 0))
"""


class Daemon:
    """What the fake `docker` was asked, the containers it holds, and the plan it follows."""

    def __init__(self, state: Path) -> None:
        self.state = state
        self.plan: dict[str, Any] = {"agents": {}}
        self.save()

    def save(self) -> None:
        (self.state / "plan.json").write_text(json.dumps(self.plan))

    def agent(self, command: str, **behaviour: Any) -> None:
        self.plan["agents"][command] = behaviour
        self.save()

    def set(self, **options: Any) -> None:
        self.plan.update(options)
        self.save()

    @property
    def calls(self) -> list[list[str]]:
        log = self.state / "calls.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def runs(self, prefix: str) -> list[list[str]]:
        return [
            c for c in self.calls if c[0] == "run" and c[c.index("--name") + 1].startswith(prefix)
        ]

    @property
    def containers(self) -> list[str]:
        """The containers the daemon still holds."""
        return sorted(p.stem for p in self.state.glob("botbox-*.json"))

    @property
    def removed(self) -> list[str]:
        return [c[-1] for c in self.calls if c[0] == "rm"]

    async def hanging(self, count: int = 1) -> None:
        async with asyncio.timeout(10):
            while len(list(self.state.glob("*.hanging"))) < count:
                await asyncio.sleep(0.01)


def token(daemon: Daemon) -> str:
    [run] = daemon.runs("botbox-agent-")
    return run[run.index("--name") + 1].removeprefix("botbox-agent-")


def homes(temp: Path) -> list[Path]:
    """The temp homes left behind; build locks live beside them for good."""
    return [path for path in temp.iterdir() if path.is_dir()]


def option(run: list[str], name: str) -> str:
    return run[run.index(name) + 1]


def volume(run: list[str], target: str) -> tuple[str, str]:
    """The host path and mode `run` mounts at `target`."""
    mounts = (run[i + 1].split(":") for i, arg in enumerate(run) if arg == "--volume")
    return next((source, mode) for source, t, mode in mounts if t == target)
