import json
import subprocess
import threading
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from botbox.agents.agent import SessionAgent
from botbox.RunResult import RunResult


def read_transcript(home: Path, pattern: str) -> dict[str, str]:
    """Each file under `home` matching `pattern`, by its path relative to `home`.

    The agent writes `home`, so a match that resolves outside it is a link to a host file and
    is skipped. The container has exited by the time this runs, so no link can change after
    the check. Bytes that aren't UTF-8 are replaced and a file that won't open is skipped, so
    the agent can't break the run's result.
    """
    root = home.resolve()
    transcript = {}
    for path in sorted(home.glob(pattern)):
        if path.is_file() and path.resolve().is_relative_to(root):
            with suppress(OSError):
                transcript[path.relative_to(home).as_posix()] = path.read_text(
                    encoding="utf-8", errors="replace"
                )
    return transcript


class Session:
    """An agent CLI held open in a locked-down container: one message in, one turn's events out.

    The CLI and anything it starts in the background live until the session closes. Closing
    sends end-of-input, waits for the CLI to exit, and returns the run's `RunResult`.
    `finish` reads the transcript and tears down the home and proxy, returning the transcript
    and the proxy log.
    """

    def __init__(
        self,
        agent: SessionAgent,
        process: subprocess.Popen[str],
        container: str,
        image: str,
        finish: Callable[[], tuple[dict[str, str], str]],
    ) -> None:
        self.agent = agent
        self.result: RunResult | None = None
        self._process = process
        self._container = container
        self._image = image
        self._finish = finish
        self._stdout: list[str] = []
        self._stderr: list[str] = []
        # Drained alongside, so a chatty stderr can't fill its pipe and stall the CLI.
        self._stderr_reader = threading.Thread(
            target=self._stderr.extend, args=(process.stderr,), daemon=True
        )
        self._stderr_reader.start()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def message(self, text: str) -> list[dict[str, Any]]:
        """Send `text` and return the turn's events, once the agent says the turn is over.

        Lines that aren't JSON objects stay in the result's stdout but aren't events. If the
        CLI exits mid-turn, the events that arrived come back; `close()` has the exit code.
        """
        stdin, stdout = self._process.stdin, self._process.stdout
        assert stdin is not None
        assert stdout is not None
        stdin.write(self.agent.encode(text) + "\n")
        stdin.flush()
        events: list[dict[str, Any]] = []
        for line in stdout:
            self._stdout.append(line)
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            events.append(event)
            if self.agent.turn_ended(event):
                break
        return events

    def close(self) -> RunResult:
        """End the CLI's input, wait for it to exit, and return what the session left."""
        if self.result is not None:
            return self.result
        stdin, stdout = self._process.stdin, self._process.stdout
        assert stdin is not None
        assert stdout is not None
        with suppress(BrokenPipeError):
            stdin.close()
        self._stdout.extend(stdout)
        exit_code = self._process.wait()
        self._stderr_reader.join()
        transcript, proxy = self._finish()
        self.result = RunResult(
            "".join(self._stdout),
            "".join(self._stderr),
            exit_code,
            transcript,
            proxy,
            self._container,
            self._image,
        )
        return self.result
