# Getting Started

Run Claude Code against a directory of failing tests, inside a locked-down container, and read back what it did.

## Install

```sh
pip install botbox
```

You need Docker, and Claude Code logged in on the host: `run()` copies `~/.claude/.credentials.json` into the container.

## Your first run

```python
from botbox import Botbox, ClaudeAgent

agent = ClaudeAgent(model="claude-opus-5", effort="high")
box = Botbox(agent)

result = box.run(
    command=agent.command("Make the failing tests pass please"),
    mounts=[
        ("./tests", "/tests", "ro"),
        ("./work", "/work", "rw"),
    ],
    workdir="/work", # optional; where the command starts. Must be a mounted path.
)

print(result.stdout)
print(result.proxy)
```

## What `run()` did

`run()` builds the image, creates a private network and a proxy sidecar, stages your credentials into a temporary home directory, runs the command, reads the transcript and proxy log out, deletes the temporary home, tears the network down, and returns.

`result.stdout` is the CLI's output. `result.proxy` is every connection the agent made, admitted or refused.

## Next steps

- [Extending the image](./guide/extending-the-image) — install the tools your task needs.
- [Allowing hosts](./guide/allowing-hosts) — let the agent reach more than its API.
- [Reading the result](./guide/reading-the-result) — transcript, proxy log, exit code.
- [Reference](./reference/) — the full API.
- [How It Works](./explanation/) — why botbox works this way.
