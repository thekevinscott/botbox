from pathlib import Path


def group_running(pgid: int) -> bool:
    """Whether any process in group `pgid` is still running. Zombies have stopped."""
    for stat in Path("/proc").glob("[0-9]*/stat"):
        try:
            state, _ppid, pgrp = stat.read_text().rsplit(")", 1)[1].split()[:3]
        except OSError:
            continue
        if pgrp == str(pgid) and state not in ("Z", "X"):
            return True
    return False
