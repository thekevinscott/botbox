import os


def preloaded(data: bytes) -> int:
    """The read end of a pipe that already holds `data` and whose write end is closed.

    Raises BlockingIOError if `data` won't fit in the pipe's buffer.
    """
    read, write = os.pipe()
    try:
        os.set_blocking(write, False)
        if os.write(write, data) != len(data):
            raise BlockingIOError(f"{len(data)} bytes do not fit in a pipe")
    except BaseException:
        os.close(read)
        raise
    finally:
        os.close(write)
    return read
