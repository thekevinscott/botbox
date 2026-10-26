"""A fake `docker` on PATH that keeps each container's state; `conftest` puts it there.

Named `_test` so the checks treat it as test code, not source.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

CREDENTIALS = '{"claudeAiOauth": {"accessToken": "t"}}'
REFUSAL = 'NOTICE Proxying refused on filtered url "github.com:443"\n'
LISTENING = "botbox-proxy: listening\n"

# Each container is a state file, `<name>.json`, that inspect reads and rm deletes. The proxy
# serves until its stdin closes; each agent does what the plan says for its command. A session
# answers each message on its stdin with an event, a line that isn't JSON, and a result.
FAKE_DOCKER = """
import json, os, signal, sys, time
from pathlib import Path

READY = b"botbox-proxy: listening\\n"

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
    source = next(source for source, t, _ in mounts if t == target)
    return Path(source) if source.startswith("/") else state / "volumes" / source


def settle(name, status, code=0):
    labels = [option("--label")] if "--label" in argv else []
    container = {"Status": status, "ExitCode": code, "Labels": labels}
    (state / f"{name}.json").write_text(json.dumps(container))


def exit_container(name, code=0):
    # A container rm already removed stays removed: r+ never recreates the file.
    try:
        with open(state / f"{name}.json", "r+") as file:
            container = json.load(file)
            container.update(Status="exited", ExitCode=code)
            file.seek(0)
            file.truncate()
            json.dump(container, file)
    except FileNotFoundError:
        pass


command = argv[0]
if command == "buildx":
    if option("--tag") in plan.get("builds_fail", ()):
        fail("ERROR: failed to solve\\n")
    sys.exit(0)
if (state / "down").exists():
    fail("Cannot connect to the Docker daemon\\n")
if command == "volume":
    if argv[1] == "create":
        (state / "volumes" / argv[-1]).mkdir(parents=True)
    else:
        for name in argv[3:]:
            path = state / "volumes" / name
            for child in path.glob("*"):
                child.unlink()
            path.rmdir()
elif command == "container":
    name = argv[-1]
    path = state / f"{name}.json"
    if not path.exists():
        fail(f"Error: No such container: {name}\\n")
    print(json.dumps([{"Name": "/" + name, "State": json.loads(path.read_text())}]))
elif command == "ps":
    for path in sorted(state.glob("botbox-*.json")):
        if option("--filter").removeprefix("label=") in json.loads(path.read_text())["Labels"]:
            print(path.stem)
elif command == "rm":
    time.sleep(plan.get("rm_seconds", 0))
    if plan.get("rm_fails"):
        fail("Error response from daemon: removal of container is already in progress\\n")
    for name in argv[2:]:
        (state / f"{name}.json").unlink(missing_ok=True)
elif option("--name").startswith("botbox-proxy-"):
    name = option("--name")
    if plan.get("proxy_fails"):
        fail("tinyproxy: bad config\\n")
    settle(name, "running")
    sys.stdout.buffer.write(READY + plan.get("proxy_log", "").encode("latin-1"))
    sys.stdout.buffer.flush()
    (volume("/run/botbox") / "proxy.sock").touch()
    sys.stdin.buffer.read()
    exit_container(name)
else:
    name = option("--name")
    agent = plan["agents"].get(argv[-1], {})
    if agent.get("missing"):
        fail("Unable to find image 'botbox-claude:latest' locally\\n", 125)
    settle(name, "running")
    try:
        session = volume("/home/user/.claude/projects") / "-work"
    except StopIteration:
        session = volume("/home/user") / ".claude" / "projects" / "-work"
    session.mkdir(parents=True, exist_ok=True)
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
                (state / f"{name}.hanging").write_text(str(os.getpid()))
                while (state / f"{name}.json").exists():
                    time.sleep(0.05)
                sys.exit(137)
            if said == "die":
                os.kill(os.getpid(), signal.SIGKILL)
            print("not json")
            print(json.dumps({"type": "result", "result": said.upper()}), flush=True)
    if mode == "hang":
        # Dies with its owner, as an agent in the proxy's PID namespace does.
        owner = os.getppid()
        (state / f"{name}.hanging").write_text(str(os.getpid()))
        while os.getppid() == owner:
            time.sleep(0.05)
        exit_container(name, 137)
        sys.exit(137)
    if mode == "daemon_gone":
        (state / "down").touch()
        print("Cannot connect to the Docker daemon", file=sys.stderr, flush=True)
        sys.exit(125)
    if mode == "client_dies":
        os.kill(os.getpid(), signal.SIGKILL)
    if mode == "client_dies_after_exit":
        exit_container(name, 0)
        os.kill(os.getpid(), signal.SIGKILL)
    exit_container(name, agent.get("exit", 0))
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
    def volumes(self) -> list[str]:
        """The volumes the daemon still holds."""
        return sorted(p.name for p in (self.state / "volumes").glob("*"))

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
    """The temp homes left behind."""
    return [path for path in temp.iterdir() if path.is_dir()]


def option(run: list[str], name: str) -> str:
    return run[run.index(name) + 1]


def volume(run: list[str], target: str) -> tuple[str, str]:
    """The host path and mode `run` mounts at `target`."""
    mounts = (run[i + 1].split(":") for i, arg in enumerate(run) if arg == "--volume")
    return next((source, mode) for source, t, mode in mounts if t == target)
