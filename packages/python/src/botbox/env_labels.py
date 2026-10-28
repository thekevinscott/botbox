from collections.abc import Mapping

ENV = "BOTBOX_LABELS"


def env_labels(environ: Mapping[str, str]) -> dict[str, str]:
    """The labels in `environ`'s `BOTBOX_LABELS`, one `key=value` per line, as in Docker's
    `--label-file`. Raises `ValueError` for a line without `=` or the reserved `botbox.run`."""
    labels = {}
    for line in environ.get(ENV, "").splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ValueError(f"{ENV} takes one key=value per line: {line!r}")
        if key == "botbox.run":
            raise ValueError(f"botbox.run is reserved for botbox cleanup, in {ENV}")
        labels[key] = value
    return labels
