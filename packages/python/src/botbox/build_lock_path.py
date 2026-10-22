import hashlib
from pathlib import Path
from tempfile import gettempdir


def build_lock_path(tag: str) -> Path:
    """The lock file for builds of `tag`, keyed by the tag and left in the system temp dir."""
    digest = hashlib.sha256(tag.encode()).hexdigest()[:12]
    return Path(gettempdir()) / f"botbox-build-{digest}.lock"
