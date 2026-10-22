import warnings
from collections.abc import Awaitable


async def warned(step: Awaitable[object], what: str) -> None:
    """Await a teardown `step`. If it fails, warn that botbox could not `what`, and carry on."""
    try:
        await step
    except Exception as error:
        warnings.warn(f"botbox could not {what}: {error}", RuntimeWarning, stacklevel=2)
