import asyncio

from botbox.docker.Capture import Capture


class CapturedLines:
    """Read lines from the legacy capture without changing its retained output."""

    def __init__(self, capture: Capture, client: asyncio.Future[int]) -> None:
        self.capture = capture
        self.client = client
        self.read = 0
        client.add_done_callback(self.ended)

    def ended(self, _client: asyncio.Future[int]) -> None:
        self.capture.grew.set()

    async def readline(self) -> bytes:
        printed, grew = self.capture.into, self.capture.grew
        while True:
            grew.clear()
            end = printed.find(b"\n", self.read)
            if end < 0:
                if not self.client.done():
                    await grew.wait()
                    continue
                if self.read == len(printed):
                    return b""
                end = len(printed)
            line = bytes(printed[self.read : end + 1])
            self.read = min(end + 1, len(printed))
            return line
