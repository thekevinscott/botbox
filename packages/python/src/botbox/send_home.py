import asyncio
import contextlib


async def send_home(stdin: asyncio.StreamWriter, home: bytes) -> None:
    """Write the agent's home archive to the relay's stdin.

    A relay that died before reading it has already said why on stderr, and its exit code
    tells the run, so a broken pipe here is left to that.
    """
    if not home:
        return
    with contextlib.suppress(BrokenPipeError, ConnectionResetError):
        stdin.write(home)
        await stdin.drain()
