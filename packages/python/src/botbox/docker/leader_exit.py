import asyncio
import os


async def leader_exit(pid: int) -> None:
    """Return once process `pid` has exited, whatever it left holding its pipes."""
    try:
        fd = os.pidfd_open(pid)
    except ProcessLookupError:
        return
    loop = asyncio.get_running_loop()
    exited = asyncio.Event()
    loop.add_reader(fd, exited.set)
    try:
        await exited.wait()
    finally:
        loop.remove_reader(fd)
        os.close(fd)
