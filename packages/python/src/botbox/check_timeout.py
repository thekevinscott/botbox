def check_timeout(timeout: float | None) -> float | None:
    """Return `timeout`, in seconds, or raise `ValueError` if it is not positive."""
    if timeout is not None and timeout <= 0:
        raise ValueError(
            f"timeout is in seconds and must be positive, or None for no limit: {timeout!r}"
        )
    return timeout
