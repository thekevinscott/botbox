"""Drop pi's repeated tool-progress snapshots from its JSON stdout stream."""

import json
import sys


def main() -> None:
    for line in sys.stdin.buffer:
        try:
            event = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            event = None
        if not isinstance(event, dict) or event.get("type") != "tool_execution_update":
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()


main()
