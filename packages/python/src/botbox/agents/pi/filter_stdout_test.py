import importlib
from io import BytesIO
from unittest.mock import Mock, patch


def describe_filter_stdout() -> None:
    def it_drops_only_tool_execution_update_events_and_preserves_other_bytes() -> None:
        stdout = (
            b'{"type":"tool_execution_start"}\n'
            b'{ "type": "tool_execution_update", "partialResult": "large" }\n'
            b'{"type":"tool_execution_end"}\n'
            b'{"type":"user"}\n'
            b'{"type":"message_update","text":"tool_execution_update"}\n'
            b"not json\n"
            b"\xff\n"
            b"last without newline"
        )
        output = BytesIO()
        with (
            patch("sys.stdin", Mock(buffer=BytesIO(stdout))),
            patch("sys.stdout", Mock(buffer=output)),
        ):
            module = importlib.import_module("botbox.agents.pi.filter_stdout")
        assert output.getvalue() == (
            b'{"type":"tool_execution_start"}\n'
            b'{"type":"tool_execution_end"}\n'
            b'{"type":"user"}\n'
            b'{"type":"message_update","text":"tool_execution_update"}\n'
            b"not json\n"
            b"\xff\n"
            b"last without newline"
        )

        output = BytesIO()
        with (
            patch("sys.stdin", Mock(buffer=BytesIO())),
            patch("sys.stdout", Mock(buffer=output)),
        ):
            importlib.reload(module)
        assert output.getvalue() == b""
