import hashlib
from pathlib import Path
from unittest.mock import patch

from botbox.build_lock_path import build_lock_path


def describe_build_lock_path() -> None:
    def it_keys_the_lock_file_by_tag_in_the_temp_dir(tmp_path: Path) -> None:
        with patch("botbox.build_lock_path.gettempdir", return_value=str(tmp_path)):
            path = build_lock_path("an-agent:latest")
        digest = hashlib.sha256(b"an-agent:latest").hexdigest()[:12]
        assert path == tmp_path / f"botbox-build-{digest}.lock"

    def it_gives_different_tags_different_files() -> None:
        assert build_lock_path("an-agent:latest") != build_lock_path("another-agent:latest")
