"""A helper, not tests: the home an agent stages, unpacked as the relay unpacks it.

Named `_test` so the checks treat it as test code, not source.
"""

import base64
import io
import tarfile
from pathlib import Path

from botbox import Agent, HomeFiles
from botbox.agents.HomeFiles import ENV


def staged_home(agent: Agent, home: Path) -> Path:
    """Stage `agent`'s files and unpack them into `home`, which is returned."""
    files = HomeFiles()
    agent.stage_auth(files)
    archive = io.BytesIO(base64.b64decode(files.env()[ENV]))
    with tarfile.open(fileobj=archive) as tar:
        tar.extractall(home, filter="data")
    return home
