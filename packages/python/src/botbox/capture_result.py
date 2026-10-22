import shutil
import warnings
from collections.abc import Callable
from pathlib import Path
from tempfile import mkdtemp

from botbox.move_transcript import move_transcript
from botbox.RunResult import RunResult


def capture_result(
    result: Callable[[Path], RunResult], home: Path, pattern: str, log: Path
) -> RunResult:
    """Make `result` on a fresh temp dir, then move the transcript out of `home` into it and
    copy the proxy's `log` in.

    Neither is read into memory. The transcript is staged beside `home`, in the run's temp dir,
    so it goes with the run's teardown. A log that won't copy is a warning and an empty log.
    """
    captured = result(Path(mkdtemp(prefix="botbox-result-")))
    try:
        move_transcript(home, pattern, home.with_name("transcript"), captured.transcript)
        try:
            shutil.copyfile(log, captured.proxy)
        except OSError as error:
            warnings.warn(
                f"botbox could not copy its proxy log: {error}", RuntimeWarning, stacklevel=2
            )
            captured.proxy.touch()
    except BaseException:
        captured.cleanup()
        raise
    return captured
