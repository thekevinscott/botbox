from botbox.RunResult import RunResult


class Timeout(TimeoutError):
    """A run that outlasted its timeout, torn down, with what it left in `result`."""

    def __init__(self, seconds: float, result: RunResult) -> None:
        self.seconds = seconds
        self.result = result
        super().__init__(f"botbox stopped the agent after its {seconds}s timeout")
