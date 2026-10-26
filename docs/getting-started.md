# Getting Started

Run Claude Code against a directory of failing tests, inside a locked-down container, and read back what it did.

## Install

```sh
pip install botbox
```

You need Docker, and Claude Code logged in on the host. To use an API key instead, see [Claude Code](./harnesses/claude#credentials).

## Your first run

```python
import asyncio
from pathlib import Path

from botbox import Botbox, ClaudeAgent


async def main() -> None:
    agent = ClaudeAgent(model="claude-opus-5", effort="high")
    output = Path("runs/first")
    async with Botbox(agent) as box:
        result = await box.run(
            command=agent.command("Make the failing tests pass please"),
            output=output, # stdout.txt, stderr.txt, proxy.log and transcripts/ land here.
            mounts=[
                ("./tests", "/tests", "ro"),
                ("./work", "/work", "rw"),
            ],
            workdir="/work", # optional; where the command starts. Must be a mounted path.
        )
    print(result.exit_code)
    print((output / "stdout.txt").read_text())
    print((output / "proxy.log").read_text())


asyncio.run(main())
```

The API is asyncio. From sync code, wrap each call in `asyncio.run(...)`.

## What came back

`result.exit_code` is the CLI's exit code. In `runs/first/`, `stdout.txt` is the CLI's output, `proxy.log` is every connection the agent made, admitted or refused, and `transcripts/` holds the agent's session files.

## Next steps

- [Extending the image](./guide/extending-the-image) — install the tools your task needs.
- [Allowing hosts](./guide/allowing-hosts) — let the agent reach more than its API.
- [Reading the result](./guide/reading-the-result) — transcript, proxy log, exit code.
- [API](./api/botbox) — the full API.
- [Harnesses](./harnesses/) — Claude Code, Codex or pi.
- [How It Works](./explanation/) — what botbox does with Docker.
