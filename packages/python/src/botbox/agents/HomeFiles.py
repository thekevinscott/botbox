import gzip
import io
import tarfile

# The relay reads this many bytes of its stdin as the files, and hands the rest to the command.
SIZE_ENV = "BOTBOX_HOME_BYTES"


class HomeFiles:
    """Files the agent's home starts with. The relay writes them in when the container starts."""

    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, int]] = {}

    def write(self, path: str, content: str | bytes, *, mode: int = 0o644) -> None:
        """Add `content` at `path`, relative to the home, with permissions `mode`."""
        self.files[path] = (content.encode() if isinstance(content, str) else content, mode)

    def archive(self) -> bytes:
        """The files as a tar.gz, for the relay's stdin; empty without files."""
        if not self.files:
            return b""
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            for path, (content, mode) in self.files.items():
                entry = tarfile.TarInfo(path)
                entry.size = len(content)
                entry.mode = mode
                archive.addfile(entry, io.BytesIO(content))
        return gzip.compress(buffer.getvalue(), mtime=0)
