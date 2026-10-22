import asyncio


def abort_writer(writer: asyncio.StreamWriter) -> None:
    """Drop what `writer` still has to send and close it, unless it has nothing left and is closing.

    Aborting a write pipe that has already closed raises on Python 3.12 and later.
    """
    transport = writer.transport
    if not transport.is_closing() or transport.get_write_buffer_size():
        transport.abort()
