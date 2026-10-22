import asyncio

from botbox.docker.leader_exit import leader_exit

POLL = 0.01


async def exit_code(process: asyncio.subprocess.Process) -> int:
    """`process`'s exit code once it exits.

    Unlike `process.wait()`, this doesn't also wait for every holder of its pipes to close them.
    """
    if process.returncode is None:
        await leader_exit(process.pid)
    while process.returncode is None:
        await asyncio.sleep(POLL)
    return process.returncode
