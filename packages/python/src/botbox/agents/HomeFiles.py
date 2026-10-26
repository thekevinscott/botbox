import base64
import io
import tarfile

ENV = "BOTBOX_HOME_FILES"
# Linux's limit on one argument, which `docker run --env NAME=VALUE` must fit in.
ARG_MAX = 128 * 1024


class HomeFiles:
    """Files the agent's home starts with. The relay writes them in when the container starts."""

    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, int]] = {}

    def write(self, path: str, content: str | bytes, *, mode: int = 0o644) -> None:
        """Add `content` at `path`, relative to the home, with permissions `mode`."""
        self.files[path] = (content.encode() if isinstance(content, str) else content, mode)

    def env(self) -> dict[str, str]:
        """The env var that carries the files to the relay, as a base64 tar; none without files.

        Raises `ValueError` if the files are too large for Docker to pass.
        """
        if not self.files:
            return {}
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            for path, (content, mode) in self.files.items():
                entry = tarfile.TarInfo(path)
                entry.size = len(content)
                entry.mode = mode
                archive.addfile(entry, io.BytesIO(content))
        value = base64.b64encode(buffer.getvalue()).decode()
        if len(ENV) + 1 + len(value) >= ARG_MAX:
            raise ValueError(f"the agent's home files are too large to pass: {len(value)} bytes")
        return {ENV: value}
