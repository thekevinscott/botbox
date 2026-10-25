import asyncio

POLL = 0.01


async def exit_code(process: asyncio.subprocess.Process) -> int:
    """`process`'s exit code once it exits.

    `process.wait()` also waits for every holder of its pipes to close them. `returncode` is set
    as soon as asyncio's child watcher sees the exit.
    """
    while process.returncode is None:
        await asyncio.sleep(POLL)
    return process.returncode
